from datetime import datetime
from itertools import chain, groupby, combinations
from typing import Dict, Iterator, List, Optional
from copy import deepcopy
from monty.json import MontyDecoder

from maggma.builders import Builder
from maggma.stores import Store

from pymatgen.core import Structure
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher, PointDefectComparator
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from atomate.utils.utils import load_class

from emmet.core.settings import EmmetSettings
from emmet.core.utils import jsanitize, get_sg
from emmet.core.defect import DefectDoc, DefectDoc2d, DefectThermoDoc
from emmet.core.cp2k.calc_types import TaskType
from emmet.core.cp2k.calc_types.utils import run_type
from emmet.core.cp2k.material import MaterialsDoc
from emmet.builders.settings import EmmetBuildSettings
from emmet.builders.cp2k.utils import get_mpid, synchronous_query

SETTINGS = EmmetSettings()

__author__ = "Nicholas Winner <nwinner@berkeley.edu>"
__maintainer__ = "Jason Munro"


class DefectBuilder(Builder):
    """
    The DefectBuilder collects task documents performed on structures containing a single point defect.
    The builder is intended to group tasks corresponding to the same defect (species including charge state),
    find the best ones, and perform finite-size defect corrections to create a defect document. These
    defect documents can then be assembled into defect phase diagrams using the DefectThermoBuilder.

    In order to make the build process easier, an entry must exist inside of the task doc that identifies it
    as a point defect calculation. Currently this is the Pymatgen defect object keyed by "defect". In the future,
    this may be changed to having a defect transformation in the transformation history.

    The process is as follows:

        1.) Find all documents containing the defect query.
        2.) Find all documents that do not contain the defect query, and which have DOS and dielectric data already
            calculated. These are the candidate bulk tasks.
        3.) For each candidate defect task, attempt to match to a candidate bulk task of the same number of sites
            (+/- 1) with the required properties for analysis. Reject defects that do not have a corresponding
            bulk calculation.
        4.) Convert (defect, bulk task) doc pairs to DefectDocs
        5.) Post-process and validate defect document
        6.) Update the defect store
    """

    # TODO: should dielectric/electronic_structure be optional or required?
    def __init__(
        self,
        tasks: Store,
        defects: Store,
        dielectric: Store,
        electronic_structure: Store,
        materials: Store,
        electrostatic_potentials: Store,
        task_validation: Optional[Store] = None,
        query: Optional[Dict] = None,
        allowed_task_types: Optional[List[str]] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        """
        Args:
            tasks: Store of task documents
            defects: Store of defect documents to generate
            query: dictionary to limit tasks to be analyzed. NOT the same as the defect_query property
            allowed_task_types: list of task_types that can be processed
            symprec: tolerance for SPGLib spacegroup finding
            ltol: StructureMatcher tuning parameter for matching tasks to materials
            stol: StructureMatcher tuning parameter for matching tasks to materials
            angle_tol: StructureMatcher tuning parameter for matching tasks to materials
        """

        self.tasks = tasks
        self.defects = defects
        self.materials = materials
        self.dielectric = dielectric
        self.electronic_structure = electronic_structure
        self.electrostatic_potentials = electrostatic_potentials

        self.task_validation = task_validation
        self.allowed_task_types = (
            [t.value for t in TaskType]
            if allowed_task_types is None
            else allowed_task_types
        )

        self._allowed_task_types = {TaskType(t) for t in self.allowed_task_types}
        self.settings = EmmetBuildSettings.autoload(settings)
        self.query = query if query else {}
        self.timestamp = None
        self.kwargs = kwargs

        sources = [tasks, dielectric, electronic_structure, materials, electrostatic_potentials]
        if self.task_validation:
            sources.append(self.task_validation)
        super().__init__(sources=sources, targets=[defects], **kwargs)

    @property
    def defect_query(self) -> str:
        """
        The standard query for defect tasks. Update this if
        schema changes in the future.

        For example, if top level key exists 'defect' can be returned.
        Alternatively, if an initial defect transformation was performed, then
        you can check via 'transformations.history.0.defect'
        """
        return 'transformations.history.0.defect'

    @property
    def identifying_defect_properties(self):
        return [
            'charge'
        ]

    @property
    def required_defect_properties(self) -> List:
        return [
            self.defect_query,
            'output.energy',
            'output.structure',
            'input',
            'transformations',
            'task_id',
            'nsites'
        ]

    @property
    def optional_defect_properties(self) -> List:
        return [
            'last_updated',
            'created_on',
            'tags'
        ]

    @property
    def required_bulk_properties(self) -> List:
        return [
            'output.energy',
            'output.structure',
            'output.vbm',
            'output.cbm',
            'input',
            'transformations',
        ]

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Basic search index for tasks
        self.tasks.ensure_index("task_id")
        self.tasks.ensure_index("last_updated")
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")

        # Search index for materials
        self.materials.ensure_index("material_id")
        self.materials.ensure_index("last_updated")
        self.materials.ensure_index("task_ids")

        # Search index for materials
        self.defects.ensure_index("material_id")
        self.defects.ensure_index("defect_id")
        self.defects.ensure_index("last_updated")
        self.defects.ensure_index("task_ids")

        if self.task_validation:
            self.task_validation.ensure_index("task_id")
            self.task_validation.ensure_index("valid")

    def prechunk(self, number_splits: int) -> Iterator[Dict]:
        raise NotImplementedError

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into defect documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the Defect Collection.

        The procedure is as follows:

            1. Get all tasks with standard "defect" query tag
            2. Filter all tasks by skipping tasks which are already in the Defect Store
            3. Get all tasks that could be used as bulk


        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Defect builder started")
        self.logger.info(
            f"Allowed task types: {[task_type.value for task_type in self._allowed_task_types]}"
        )

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime for material documents
        self.timestamp = datetime.utcnow()

        # Get all tasks
        self.logger.info("Finding tasks to process")
        temp_query = dict(self.query)
        temp_query["state"] = "successful"

        all_tasks = {
            doc[self.tasks.key]
            for doc in self.tasks.query(criteria=temp_query, properties=[self.tasks.key])
        }

        temp_query = {
            "$and": [
                temp_query, 
                {self.defect_query: {'$exists': True}}, 
                {d: {'$exists': True} for d in self.required_defect_properties}
                ]
            }
        defect_tasks = {
            doc[self.tasks.key]
            for doc in self.tasks.query(criteria=temp_query, properties=[self.tasks.key])
        }

        processed_defect_tasks = {
            t_id
            for d in self.defects.query({}, ["task_ids"])
            for t_id in d.get("task_ids", [])
        }

        self.logger.debug("All tasks: {}".format(len(all_tasks)))
        self.logger.debug("Bulk tasks before filter: {}".format(len(all_tasks-defect_tasks)))
        bulk_tasks = set(filter(self.__preprocess_bulk, all_tasks - defect_tasks))
        self.logger.debug("Bulk tasks after filter: {}".format(len(bulk_tasks)))
        self.logger.debug("All defect tasks: {}".format(len(defect_tasks)))
        unprocessed_defect_tasks = defect_tasks - processed_defect_tasks

        if not unprocessed_defect_tasks:
            self.logger.info("No unprocessed to tasks. Exiting")
            return
        elif not bulk_tasks:
            self.logger.info("No compatible bulk calculations. Exiting.")
            return

        self.logger.info(f"Found {len(unprocessed_defect_tasks)} unprocessed defect tasks")
        self.logger.info(f"Found {len(bulk_tasks)} bulk tasks with dielectric properties")

        # Set total for builder bars to have a total
        self.total = len(unprocessed_defect_tasks)

        if self.task_validation:
            invalid_ids = {
                doc[self.tasks.key]
                for doc in self.task_validation.query(
                    {"is_valid": False}, [self.task_validation.key]
                )
            }
            for t in bulk_tasks.union(unprocessed_defect_tasks):
                for doc in self.tasks.query({self.tasks.key: t}):
                    if t in invalid_ids:
                        doc["is_valid"] = False
                    else:
                        doc["is_valid"] = True

        # yield list of defects that are of the same type, matched to an appropriate bulk calc
        self.logger.info(f"Starting defect matching.")

        for defect, defect_task_group in self.__filter_and_group_tasks(unprocessed_defect_tasks):
            yield self.__get_defect_doc(defect), self.__get_item_bundle(bulk_tasks, defect_task_group)

    def process_item(self, items):
        """
        Process a group of defect tasks that correspond to the same defect into a single defect
        document. If the DefectDoc already exists, then update it and return it. If it does not,
        create a new DefectDoc

        Args:
            items: (DefectDoc or None, [(defect task dict, bulk task dict, dielectric dict), ... ]

        returns: the defect document as a dictionary
        """
        defect_doc, item_bundle = items
        self.logger.info(f"Processing group of {len(item_bundle)} defects into DefectDoc")
        if item_bundle:
            material_id = self._get_mpid(Structure.from_dict(item_bundle[0][1]['output']['structure']))  # TODO more mpid messes..
            print("THE MATRIAL ID I FOUND IS ", material_id)
            if defect_doc:
                defect_doc.update_all(item_bundle, query=self.defect_query)
            else:
                defect_doc = DefectDoc.from_tasks(tasks=item_bundle, query=self.defect_query, material_id=material_id)
            return defect_doc.dict()

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection
        """

        items = [item for item in items if item]

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} defects")
            for item in items:
                item.update({"_bt": self.timestamp})
                self.defects.remove_docs(
                    {
                       "task_ids": item['task_ids'],
                    }
                )
            self.defects.update(
                docs=jsanitize(items, allow_bson=True),
                key='task_ids',
            )
        else:
            self.logger.info("No items to update")

    def __filter_and_group_tasks(self, tasks):
        """
        Groups defect tasks. Tasks are grouped according to the reduced representation
        of the defect, and so tasks with different settings (e.g. supercell size, functional)
        will be grouped together.

        Args:
            tasks: task_ids for unprocessed defects

        returns:
            [ (defect, [task_ids] ), ...] where task_ids correspond to the same defect
        """

        props = [
            #self.defect_query,
            'transformations',
            'task_id',
            'output.structure'
        ]

        self.logger.debug(f"Finding equivalent tasks for {len(tasks)} defects")

        pdc = PointDefectComparator(check_charge=True, check_primitive_cell=True, check_lattice_scale=False)
        sm = StructureMatcher(
            ltol=self.settings.LTOL, stol=self.settings.STOL,
            angle_tol=self.settings.ANGLE_TOL, allow_subset=False
        )
        defects = [
            {
                'task_id': t['task_id'], 'defect': self.__get_defect_from_task(t),
                'structure': Structure.from_dict(t['output']['structure'])
            }
            for t in self.tasks.query(criteria={'task_id': {'$in': list(tasks)}}, properties=props)
        ]
        for d in defects:
            # TODO remove oxidation state because spins/oxidation cause errors in comparison.
            #  but they shouldnt if those props are close in value
            d['structure'].remove_oxidation_states()

        def key(x):
            s = x.get('defect').bulk_structure
            return get_sg(s), s.composition.reduced_composition

        def are_equal(x, y):
            """
            To decide if defects are equal. Either the defect objects are
            equal, OR two different defect objects relaxed to the same final structure
            (common with interstitials).

            TODO Need a way to do the output structure comparison for a X atom defect cell
            TODO which can be embedded in a Y atom defect cell up to tolerance.
            """
            if pdc.are_equal(x['defect'], y['defect']):
                return True

            # TODO This is needed for ghost vacancy unfortunately, since  sm.fit can't distinguish ghosts
            if x['defect'].defect_composition == y['defect'].defect_composition and \
                    x['defect'].charge == y['defect'].charge and \
                    sm.fit(x['structure'], y['structure']):
                return True
            return False

        sorted_s_list = sorted(enumerate(defects), key=lambda x: key(x[1]))
        all_groups = []

        # For each pre-grouped list of structures, perform actual matching.
        for k, g in groupby(sorted_s_list, key=lambda x: key(x[1])):
            unmatched = list(g)
            while len(unmatched) > 0:
                i, refs = unmatched.pop(0)
                matches = [i]
                inds = list(filter(lambda j: are_equal(refs, unmatched[j][1]), list(range(len(unmatched)))))
                matches.extend([unmatched[i][0] for i in inds])
                unmatched = [unmatched[i] for i in range(len(unmatched)) if i not in inds]
                all_groups.append(
                    (defects[i]['defect'], [defects[i]['task_id'] for i in matches])
                )

        self.logger.debug(f"All groups {all_groups}")
        return all_groups

    def __get_defect_from_task(self, task):
        """
        Using the defect_query property, retrieve a pymatgen defect object from the task document
        """
        defect = unpack(self.defect_query.split('.'), task)
        needed_keys = ['@module', '@class', 'structure', 'defect_site', 'charge', 'site_name']
        return MontyDecoder().process_decoded({k: v for k, v in defect.items() if k in needed_keys})

    def __get_defect_doc(self, defect):
        """
        Given a defect, find the DefectDoc corresponding to it in the defects store if it exists

        returns: DefectDoc or None
        """
        material_id = self._get_mpid(defect.bulk_structure)
        docs = [
            DefectDoc(**doc)
            for doc in self.defects.query(criteria={'material_id': material_id}, properties=None)
        ]
        pdc = PointDefectComparator(check_charge=True, check_primitive_cell=True, check_lattice_scale=True)
        for doc in docs:
            if pdc.are_equal(defect, doc.defect):
                return doc
        return None

    def __get_dielectric(self, task_id):
        """
        Given a bulk task's task_id, find the material_id, and then use it to query the dielectric store
        and retrieve the total dielectric tensor for defect analysis. If no dielectric exists, as would
        be the case for metallic systems, return None.
        """
        t = next(self.tasks.query(criteria={'task_id': task_id}, properties=['output.structure']))
        struc = Structure.from_dict(t.get('output').get('structure'))
        self.logger.debug("Finding dielectric for task_id {} for MPID {}".format(task_id, self._get_mpid(struc)))
        for diel in self.dielectric.query(criteria={self.dielectric.key: self._get_mpid(struc)}, properties=['dielectric.total']):
            return diel['dielectric']['total']
        return None

    def __get_item_bundle(self, bulk_tasks, defect_task_group):
        """
        Gets a group of items that can be processed together into a defect document.

        Args:
            bulk_tasks: possible bulk tasks to match to defects
            defect_task_group: group of equivalent defects (defined by PointDefectComparator)

        returns: [(defect task dict, bulk_task_dict, dielectric dict), ...]
        """
        return [
            (
                next(synchronous_query(self.tasks, self.electrostatic_potentials, query={'task_id': defect_tasks_id}, properties=None)),
                next(synchronous_query(self.tasks, self.electrostatic_potentials, query={'task_id': bulk_tasks_id}, properties=None)),
                self.__get_dielectric(bulk_tasks_id),
            )
            for defect_tasks_id, bulk_tasks_id
            in self.__match_defects_to_bulks(bulk_tasks, defect_task_group)
        ]

    # TODO NEED TO GET FORM EN FOR SORTING FROM MATDOC
    def _get_mpid(self, structure):
        """
        Given a structure, determine if an equivalent structure exists, with a material_id,
        in the materials store.

        Args:
            structure: Candidate structure

        returns: material_id, if one exists, else None
        """
        sga = SpacegroupAnalyzer(structure)
        mats = self.materials.query(
            criteria={
                'chemsys': structure.composition.chemical_system,
                'symmetry.symbol': sga.get_space_group_symbol()
            }, properties=['structure', 'material_id']
        )
        sm = StructureMatcher()
        for m in mats:
            if sm.fit(structure, Structure.from_dict(m['structure'])):
                return m['material_id']
        return None

    def __match_defects_to_bulks(self, bulk_ids, defect_ids):
        """
        Given task_ids of bulk and defect tasks, match the defects to a bulk task that has
        commensurate:

            - Composition
            - Number of sites
            - Symmetry

        """

        self.logger.debug(f"Finding bulk/defect task combinations.")
        self.logger.debug(f"Bulk tasks: {bulk_ids}")
        self.logger.debug(f"Defect tasks: {defect_ids}")

        props = [
            'task_id',
            'input',
            'nsites',
            'output.structure',
            'transformations',
            'defect',
            'scale',
        ]
        defects = list(self.tasks.query(criteria={'task_id': {'$in': list(defect_ids)}}, properties=props))
        ps = DefectBuilder.__get_pristine_supercell(defects[0])
        bulks = list(
            self.tasks.query(
                criteria={
                    'task_id': {'$in': list(bulk_ids)},
                    'composition_reduced': ps.composition.reduced_composition.as_dict(),
                },
                properties=props
            )
        )

        sm = StructureMatcher(
            ltol=SETTINGS.LTOL,
            stol=SETTINGS.STOL,
            angle_tol=SETTINGS.ANGLE_TOL,
            primitive_cell=False,
            scale=True,
            attempt_supercell=True,
            allow_subset=False,
            comparator=ElementComparator(),
        )

        # TODO I think the secondary (nsites) comparison might have some edge case issues
        def _compare(b, d):
            if run_type(b.get('input').get('dft')).value.split('+U')[0] == \
                run_type(d.get('input').get('dft')).value.split('+U')[0] and \
                    sm.fit(DefectBuilder.__get_pristine_supercell(d), DefectBuilder.__get_pristine_supercell(b)):
                if abs(b['nsites'] - d['nsites']) <= 1:
                    return True
            return False

        # TODO This loop will terminate the match when the first bulk match for a defect is found. This should 
        # be fine if we can ensure that the commenserate bulks are all the same given they both compare True.
        # Need to double check that they really are the same.
        pairs = []
        for defect in defects:
            for bulk in bulks:
                if _compare(bulk, defect):
                    pairs.append((defect['task_id'], bulk['task_id']))
                    break

        self.logger.debug(f"Found {len(pairs)} commensurate bulk/defect pairs")
        return pairs

    def __preprocess_bulk(self, task):
        """
        Given a TaskDoc that could be a bulk for defect analysis, check to see if it can be used. Bulk
        tasks must have:

            (1) Correspond to an existing material_id in the materials store
            (2) If the bulk is not a metal, then the dielectric tensor must exist in the dielectric store

        """
        t = next(self.tasks.query(criteria={'task_id': task}, properties=['output.structure', 'mpid']))

        # TODO: This is for my personal use to get around the 2D materials problem. Should not be made official

        if 'ML' in t['mpid']:
            self.logger.debug(f"Found monolayer for...")
            mpid = t['mpid'].split('-ML')[0]
        else:
            struc = Structure.from_dict(t.get('output').get('structure'))
            mpid = self._get_mpid(struc)
            if not mpid:
                return False
        self.logger.debug(f"Material ID: {mpid}")

        elec = next(self.electronic_structure.query(properties=None, criteria={"material_id": mpid}))
        dos = MontyDecoder().process_decoded({k: v for k, v in elec.items()})
        if dos.get_gap():
            diel = list(self.dielectric.query(criteria={self.dielectric.key: mpid}))
            if not diel:
                self.logger.info(f"Task {task} for {mpid} ({struc.composition.reduced_formula}) requires "
                                 f"dielectric properties, but none found in dielectric store")
                return False

        return True

    @staticmethod
    def __get_pristine_supercell(task):
        """
        Given a task document for a defect calculation, retrieve the un-defective, pristine supercell.
        If defect cannot be found in task, return the input structure.
        """
        if task.get('defect'):
            return load_class(
                task['defect']['@module'], task['defect']['@class']
            ).from_dict(task['defect']).bulk_structure
        elif task.get('transformations'):
            return Structure.from_dict(task['transformations']['history'][0]['input_structure'])
        return Structure.from_dict(task['input']['structure'])


# TODO This needs to be unified into one builder somehow
class DefectBuilder2d(DefectBuilder):

    def process_item(self, items):
        """
        Process a group of defect tasks that correspond to the same defect into a single defect
        document. If the DefectDoc already exists, then update it and return it. If it does not,
        create a new DefectDoc

        Args:
            items: (DefectDoc or None, [(defect task dict, bulk task dict, dielectric dict), ... ]

        returns: the defect document as a dictionary
        """
        defect_doc, item_bundle = items
        self.logger.info(f"Processing group of {len(item_bundle)} defects into DefectDoc")
        if item_bundle:
            material_id = self._get_mpid(Structure.from_dict(item_bundle[0][1]['output']['structure']))  # TODO more mpid messes..
            if defect_doc:
                defect_doc.update_all(item_bundle, query=self.defect_query)
            else:
                defect_doc = DefectDoc2d.from_tasks(tasks=item_bundle, query=self.defect_query, material_id=material_id)
            return defect_doc.dict()


class DefectThermoBuilder(Builder):

    """
    This builder creates collections of the DefectThermoDoc object.

        (1) Find all DefectDocs that correspond to the same bulk material
            given by material_id
        (2) Create a new DefectThermoDoc for all of those documents
        (3) Insert/Update the defect_thermos store with the new documents
    """

    def __init__(
            self,
            defects: Store,
            defect_thermos: Store,
            materials: Store,
            electronic_structures: Store,
            query: Optional[Dict] = None,
            **kwargs,
    ):
        """
        Args:
            defects: Store of defect documents (generated by DefectBuilder)
            defect_thermos: Store of DefectThermoDocs to generate.
            materials: Store of MaterialDocs to construct phase diagram
            electronic_structures: Store of DOS objects
            query: dictionary to limit tasks to be analyzed
        """

        self.defects = defects
        self.defect_thermos = defect_thermos
        self.materials = materials
        self.electronic_structures = electronic_structures

        self.query = query if query else {}
        self.timestamp = None
        self.kwargs = kwargs

        super().__init__(sources=[defects, materials, electronic_structures], targets=[defect_thermos], **kwargs)

    def ensure_indexes(self):
        """
        Ensures indicies on the collections
        """

        # Basic search index for tasks
        self.defects.ensure_index("material_id")
        self.defects.ensure_index("defect_id")

        # Search index for materials
        self.defect_thermos.ensure_index("material_id")

    # TODO need to only process new tasks. Fast builder so currently is OK for small collections
    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets items to process into DefectThermoDocs.

        returns:
            iterator yielding tuples containing:
                - group of DefectDocs belonging to the same bulk material as indexed by material_id,
                - materials in the chemsys of the bulk material for constructing phase diagram
                - Dos of the bulk material for constructing phase diagrams/getting doping

        """

        self.logger.info("Defect thermo builder started")
        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark build time for defect thermo documents
        self.timestamp = datetime.utcnow()

        # Get all tasks
        self.logger.info("Finding tasks to process")
        temp_query = dict(self.query)
        temp_query["state"] = "successful"

        #unprocessed_defect_tasks = all_tasks - processed_defect_tasks

        all_docs = [doc for doc in self.defects.query(self.query)]

        def filterfunc(x):
            # material for defect x exists
            if not list(self.materials.query(criteria={'material_id': x['material_id']}, properties=None)):
                return False

            # All chempots exist in material store
            if not all(
                bool(list(self.materials.query(criteria={'chemsys': str(el)}, properties=None)))
                for el in
                load_class(x['defect']['@module'], x['defect']['@class']).from_dict(x['defect']).defect_composition
            ):
                return False

            return True

        for key, group in groupby(
                filter(
                    filterfunc,
                    sorted(all_docs, key=lambda x: x['material_id'])
                ), key=lambda x: x['material_id']
        ):
            group = [g for g in group]
            try:
                yield (group, self.__get_materials(key), self.__get_electronic_structure(group))
            except LookupError as exception:
                raise exception

    def process_item(self, docs):
        """
        Process a group of defects belonging to the same material into a defect thermo doc
        """
        self.logger.info(f"Processing defects")
        defects, materials, elec_struc = docs
        defects = [DefectDoc(**d) for d in defects]
        materials = [MaterialsDoc(**m) for m in materials]
        defect_thermo_doc = DefectThermoDoc.from_docs(defects, materials=materials, electronic_structure=elec_struc)
        return defect_thermo_doc.dict()

    def update_targets(self, items):
        """
        Inserts the new DefectThermoDocs into the defect_thermos store
        """
        items = [item for item in items if item]
        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} defect thermo docs")
            self.defect_thermos.update(
                docs=jsanitize(items, allow_bson=True),
                key=self.defect_thermos.key,
            )
        else:
            self.logger.info("No items to update")

    def __get_electronic_structure(self, group):
        return next(self.electronic_structures.query(criteria={'material_id': group[0]['material_id']}, properties=None))

    def __get_materials(self, key) -> List:
        """
        Given a group of DefectDocs, use the bulk material_id to get materials in the chemsys from the
        materials store.
        """
        bulk = list(self.materials.query(criteria={'material_id': key}, properties=None))
        if not bulk:
            raise LookupError(
                f"The bulk material ({key}) for these defects cannot be found in the materials store"
            )
        elements = bulk[0]['chemsys']

        if isinstance(elements, str):
            elements = elements.split("-")

        return list(chain(self.materials.query(criteria={"chemsys": {"$in": elements}}, properties=None), bulk))


def unpack(query, d):
    """
    Unpack a mongo-style query into dictionary retrieval
    """
    if not query:
        return d
    if isinstance(d, List):
        return unpack(query[1:], d.__getitem__(int(query.pop(0))))
    return unpack(query[1:], d.__getitem__(query.pop(0)))
