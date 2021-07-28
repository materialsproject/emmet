from datetime import datetime
from itertools import chain, groupby, combinations
from operator import itemgetter
from typing import Dict, Iterator, List, Optional
import numpy as np

from maggma.builders import Builder
from maggma.stores import Store
from pymatgen.core import Structure
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher, PointDefectComparator
from atomate.utils.utils import load_class

from pymatgen.analysis.defects.core import (
    Defect, Vacancy, Substitution, Polaron, Interstitial, GhostVacancy, DefectEntry
)
from pymatgen.analysis.defects.defect_compatibility import DefectCompatibility
from monty.json import MontyDecoder

from emmet.builders.utils import maximal_spanning_non_intersecting_subsets
from emmet.builders.cp2k.utils import matcher, get_dielectric, get_mpid
from emmet.core import SETTINGS
from emmet.core.utils import jsanitize, get_sg
from emmet.core.cp2k.calc_types import TaskType
from emmet.core.cp2k.material import MaterialsDoc
from emmet.core.cp2k.task import TaskDocument
from emmet.stubs import ComputedEntry
from emmet.core.cp2k.calc_types.utils import run_type
from emmet.core.defect import DefectDoc, DefectThermoDoc

from pymatgen.ext.matproj import MPRester
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

__author__ = "Nicholas Winner <nwinner@berkeley.edu>"
__maintainer__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class DefectBuilder(Builder):
    """
    The Materials Builder matches VASP task documents by structure similarity into materials
    document. The purpose of this builder is group calculations and determine the best structure.
    All other properties are derived from other builders.

    The process is as follows:

        1.) Find all documents with the same formula
        2.) Select only task documents for the task_types we can select properties from
        3.) Aggregate task documents based on structure similarity
        4.) Convert task docs to property docs with metadata for selection and aggregation
        5.) Select the best property doc for each property
        6.) Build material document from best property docs
        7.) Post-process material document
        8.) Validate material document

    """

    def __init__(
        self,
        tasks: Store,
        defects: Store,
        task_validation: Optional[Store] = None,
        query: Optional[Dict] = None,
        allowed_task_types: Optional[List[str]] = None,
        symprec: float = SETTINGS.SYMPREC,
        ltol: float = SETTINGS.LTOL,
        stol: float = SETTINGS.STOL,
        angle_tol: float = SETTINGS.ANGLE_TOL,
        **kwargs,
    ):
        """
        Args:
            tasks: Store of task documents
            defects: Store of defect documents to generate
            query: dictionary to limit tasks to be analyzed
            allowed_task_types: list of task_types that can be processed
            symprec: tolerance for SPGLib spacegroup finding
            ltol: StructureMatcher tuning parameter for matching tasks to materials
            stol: StructureMatcher tuning parameter for matching tasks to materials
            angle_tol: StructureMatcher tuning parameter for matching tasks to materials
        """

        self.tasks = tasks
        self.tasks.key = 'task_id'
        self.defects = defects
        self.defects.key = 'task_ids'
        self.task_validation = task_validation
        self.allowed_task_types = (
            [t.value for t in TaskType]
            if allowed_task_types is None
            else allowed_task_types
        )

        self._allowed_task_types = {TaskType(t) for t in self.allowed_task_types}

        self.query = query if query else {}
        self.symprec = symprec
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.kwargs = kwargs

        sources = [tasks]
        if self.task_validation:
            sources.append(self.task_validation)
        super().__init__(sources=sources, targets=[defects], **kwargs)

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
        self.defects.ensure_index("material_id")
        self.defects.ensure_index("last_updated")
        self.defects.ensure_index("sandboxes")
        self.defects.ensure_index("task_ids")

        if self.task_validation:
            self.task_validation.ensure_index("task_id")
            self.task_validation.ensure_index("valid")

    @property
    def defect_query(self) -> str:
        """
        The standard query for defect tasks. Update this if
        schema changes in the future.

        For example, if top level key exists 'defect' can be returned.
        Alternatively, if an initial defect transformation was performed, then
        you can check via 'transformations.history.0.defect'
        """
        return 'defect'

    @property
    def required_defect_properties(self) -> List:
        return [
            self.defect_query,
            'output.energy',
            'output.v_hartree_grid',
            'output.v_hartree',
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
            'output.v_hartree_grid',
            'output.v_hartree',
            'output.structure',
            'output.vbm',
            'output.cbm',
            'input',
            'transformations',
        ]

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

        temp_query.update({self.defect_query: {'$exists': True}})
        temp_query.update({d: {'$exists': True} for d in self.required_defect_properties})
        defect_tasks = {
            doc[self.tasks.key]
            for doc in self.tasks.query(criteria=temp_query, properties=[self.tasks.key])
        }

        processed_defect_tasks = {
            t_id
            for d in self.defects.query({}, ["task_ids"])
            for t_id in d.get("task_ids", [])
        }

        bulk_tasks = set(filter(self.preprocess_bulk, all_tasks - defect_tasks))
        unprocessed_defect_tasks = defect_tasks - processed_defect_tasks

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
        else:
            invalid_ids = set()

        for t in bulk_tasks.union(unprocessed_defect_tasks):
            for doc in self.tasks.query({self.tasks.key: t}):
                if t in invalid_ids:
                    doc["is_valid"] = False
                else:
                    doc["is_valid"] = True

        # yield list of defects that are of the same type, matched to an appropriate bulk calc
        self.logger.debug(f"Processing ")

        grouped_pairs = [
            [
                (
                    next(self.tasks.query({'task_id': defect_tasks_id}, properties=None)),
                    next(self.tasks.query({'task_id': bulk_tasks_id}, properties=None))
                )
                for defect_tasks_id, bulk_tasks_id in self.match_defects_to_bulks(bulk_tasks, defect_task_group)
            ] for defect_task_group in self.filter_and_group_tasks(defect_tasks)
        ]

        yield grouped_pairs

    def preprocess_bulk(self, task):
        t = next(self.tasks.query(criteria={'task_id': task}, properties=['output.structure']))
        struc = Structure.from_dict(t.get('output').get('structure'))
        mpid = get_mpid(struc)
        if not mpid:
            self.logger.debug(f"NO MPID FOUND FOR {task} - {struc.composition}")
            return False
        diel = get_dielectric(mpid)
        if diel is None:
            self.logger.debug(f"NO DIEL FOUND FOR {task} - {struc.composition}")
            return False
        return True

    def filter_and_group_tasks(self, tasks):
        """
        Groups defect tasks. Tasks are grouped according to the reduced representation
        of the defect, and so tasks with different settings (e.g. supercell size, functional)
        will be grouped together.

        Args:
            defect_ids: task_ids for unprocessed defects

        returns:
            generator for groups of task_ids that correspond to the same defect
        """

        props = [
            self.defect_query,
            'task_id'
        ]

        self.logger.debug(f"Finding equivalent tasks for {len(tasks)} defects")

        pdc = PointDefectComparator(check_charge=True, check_primitive_cell=True, check_lattice_scale=False)
        defects = [
            {'task_id': t['task_id'], 'defect': self.get_defect_from_task(t)}
            for t in self.tasks.query(criteria={'task_id': {'$in': list(tasks)}}, properties=props)
        ]

        def key(x):
            s = x.get('defect').bulk_structure
            return get_sg(s), s.composition.reduced_composition

        sorted_s_list = sorted(enumerate(defects), key=lambda x: key(x[1]))
        all_groups = []

        # For each pre-grouped list of structures, perform actual matching.
        for k, g in groupby(sorted_s_list, key=lambda x: key(x[1])):
            unmatched = list(g)
            while len(unmatched) > 0:
                i, refs = unmatched.pop(0)
                matches = [i]

                inds = filter(
                    lambda i: pdc.are_equal(refs['defect'], unmatched[i][1]['defect']),
                    list(range(len(unmatched))),
                )

                inds = list(inds)
                matches.extend([unmatched[i][0] for i in inds])
                unmatched = [unmatched[i] for i in range(len(unmatched)) if i not in inds]
                all_groups.append([defects[i]['task_id'] for i in matches])

        self.logger.debug(f"All groups {all_groups}")
        return all_groups

    def match_defects_to_bulks(self, bulk_ids, defect_ids):
        """
        Given task_ids of bulk and defect tasks, match the defects to a bulk task that has
        commensurate:

            - Composition
            - Number of sites
            - Symmetry

        """

        self.logger.debug(f"Finding bulk/defect task combinations.")

        props = [
            'task_id',
            'input',
            'nsites',
            'output.structure'
            'transformations',
            'defect',
            'scale',
        ]

        bulks = list(self.tasks.query(criteria={'task_id': {'$in': list(bulk_ids)}}, properties=props))
        defects = list(self.tasks.query(criteria={'task_id': {'$in': list(defect_ids)}}, properties=props))

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

        def _compare(b, d):
            if run_type(b.get('input').get('dft')).value.split('+U')[0] == \
                run_type(d.get('input').get('dft')).value.split('+U')[0] and \
                    sm.fit(DefectBuilder.get_pristine_supercell(d), DefectBuilder.get_pristine_supercell(b)):
                if abs(b['nsites'] - d['nsites']) <= 1:
                    return True
            return False

        pairs = [(defect['task_id'], bulk['task_id']) for bulk in bulks for defect in defects if _compare(bulk, defect)]
        self.logger.debug(f"Found {len(pairs)} commensurate bulk/defect pairs")
        return pairs

    @staticmethod
    def get_pristine_supercell(x):
        if x.get('defect'):
            return load_class(x['defect']['@module'], x['defect']['@class']).from_dict(x['defect']).bulk_structure
        elif x.get('transformations'):
            return Structure.from_dict(x['transformations']['history'][0]['input_structure'])
        return Structure.from_dict(x['input']['structure'])

    def process_item(self, tasks):
        """
        """
        self.logger.debug(f"Processing tasks")
        for group in tasks:
            self.logger.info(f"Processing group of size {len(group)}")

        defect_docs = [DefectDoc.from_tasks(tasks=defect_group, query=self.defect_query) for defect_group in tasks if defect_group]

        self.logger.debug(f"Produced {len(defect_docs)} ")
        return [d.dict() for d in defect_docs]

    def get_defect_from_task(self, task):
        defect = unpack(self.defect_query.split('.'), task)
        needed_keys = ['@module', '@class', 'structure', 'defect_site', 'charge', 'site_name']
        return MontyDecoder().process_decoded({k: v for k, v in defect.items() if k in needed_keys})

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection
        """

        items = [item for item in chain.from_iterable(items) if item]

        for item in items:
            item.update({"_bt": self.timestamp})

        task_ids = list(chain.from_iterable([item['task_ids'] for item in items]))

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} defects")
            self.defects.remove_docs({self.defects.key: {"$in": task_ids}})
            self.defects.update(
                docs=jsanitize(items, allow_bson=True),
                key='task_ids',
            )
        else:
            self.logger.info("No items to update")


class DefectThermoBuilder(Builder):

    def __init__(
            self,
            defects: Store,
            defect_thermos: Store,
            materials: Store,
            query: Optional[Dict] = None,
            symprec: float = SETTINGS.SYMPREC,
            ltol: float = SETTINGS.LTOL,
            stol: float = SETTINGS.STOL,
            angle_tol: float = SETTINGS.ANGLE_TOL,
            **kwargs,
    ):
        """
        Args:
            defects: Store of defect documents (generated by DefectBuilder)
            defect_thermos: Store of DefectThermoDocs to generate.
            materials: Store of MaterialDocs to construct phase diagram
            query: dictionary to limit tasks to be analyzed
            allowed_task_types: list of task_types that can be processed
            symprec: tolerance for SPGLib spacegroup finding
            ltol: StructureMatcher tuning parameter for matching tasks to materials
            stol: StructureMatcher tuning parameter for matching tasks to materials
            angle_tol: StructureMatcher tuning parameter for matching tasks to materials
        """

        self.defects = defects
        self.defect_thermos = defect_thermos
        self.materials = materials

        self.query = query if query else {}
        self.symprec = symprec
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.kwargs = kwargs

        super().__init__(sources=[defects], targets=[defect_thermos], **kwargs)

    def connect(self):
        """
        Connect to the builder sources and targets.
        """
        for s in [self.defects, self.defect_thermos, self.materials]:
            s.connect()

    @property
    def defect_doc_query(self):
        return 'material_id'

    def ensure_indexes(self):
        """
        Ensures indicies on the collections
        """

        # Basic search index for tasks
        self.defects.ensure_index("material_id")

        # Search index for materials
        self.defects.ensure_index("material_id")

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets items to process into DefectThermoDocs.

        returns:
            iterator yielding tuples containing:
                - group of DefectDocs belonging to the same bulk material as indexed by material_id,
                - materials in the chemsys of the bulk material for constructing phase diagram

        """

        self.logger.info("Defect thermo builder started")
        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark build time for defect thermo documents
        self.timestamp = datetime.utcnow()

        # Get all tasks
        self.logger.info("Finding defect docs to process")

        all_docs = [doc for doc in self.defects.query()]
        for key, group in groupby(sorted(all_docs, key=lambda x: x['material_id']), key=lambda x: x['material_id']):
            group = [g for g in group]
            yield (group, self.get_materials(group))

    def get_materials(self, group) -> List:
        """
        Given a group of DefectDocs, use the bulk material_id to get materials in the chemsys from the
        materials store.
        """
        bulk = self.materials.query(criteria={'material_id': group[0]['material_id']}, properties=None)
        elements = group[0]['chemsys']

        if isinstance(elements, str):
            elements = elements.split("-")

        all_chemsyses = []
        for i in range(len(elements)):
            for els in combinations(elements, i + 1):
                all_chemsyses.append("-".join(sorted(els)))

        return list(chain(self.materials.query(criteria={"chemsys": {"$in": all_chemsyses}}, properties=None), bulk))

    def process_item(self, docs):
        """
        Process a group of defects belonging to the same material into a defect thermo doc
        :param item:
        :return:
        """
        self.logger.info(f"Processing defects")
        defects, materials = docs
        defects = [DefectDoc(**d) for d in defects]
        materials = [MaterialsDoc(**m) for m in materials]
        defect_thermo_doc = DefectThermoDoc.from_docs(defects, materials=materials)
        return defect_thermo_doc.dict()

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection
        """

        #item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} defect thermo docs")
            #self.defects.remove_docs({self.defects.key: {"$in": task_ids}})
            self.defect_thermos.update(
                docs=jsanitize(items, allow_bson=True),
                key='material_id',
            )
        else:
            self.logger.info("No items to update")


def unpack(query, d):
    if not query:
        return d
    if isinstance(d, List):
        return unpack(query[1:], d.__getitem__(int(query.pop(0))))
    return unpack(query[1:], d.__getitem__(query.pop(0)))




