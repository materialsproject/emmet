import os
from datetime import datetime
from itertools import chain, groupby
import numpy as np

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from maggma.builders import Builder
from emmet.vasp.task_tagger import task_type
from emmet.common.utils import load_settings
from pydash.objects import get, set_, has

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
default_mat_settings = os.path.join(module_dir, "settings", "materials_settings.json")


class MaterialsBuilder(Builder):
    def __init__(self,
                 tasks,
                 materials,
                 mat_prefix="mp-",
                 materials_settings=None,
                 query=None,
                 ltol=0.2,
                 stol=0.3,
                 angle_tol=5,
                 separate_mag_orderings=False,
                 require_structure_opt=True,
                 **kwargs):
        """
        Creates a materials collection from tasks and tags

        Args:
            tasks (Store): Store of task documents
            materials (Store): Store of materials documents to generate
            mat_prefix (str): prefix for all materials ids
            materials_settings (Path): Path to settings files
            query (dict): dictionary to limit tasks to be analyzed
            ltol (float): StructureMatcher tuning parameter for matching tasks to materials
            stol (float): StructureMatcher tuning parameter for matching tasks to materials
            angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
            separate_mag_orderings (bool): Separate magnetic orderings into different materials
            require_structure_opt (bool): Requires every material have a structure optimization
        """

        self.tasks = tasks
        self.materials_settings = materials_settings
        self.materials = materials
        self.mat_prefix = mat_prefix
        self.query = query if query else {}
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.separate_mag_orderings = separate_mag_orderings
        self.require_structure_opt = require_structure_opt

        self.__settings = load_settings(self.materials_settings, default_mat_settings)

        self.allowed_tasks = {t_type for d in self.__settings for t_type in d["quality_score"]}

        super().__init__(sources=[tasks], targets=[materials], **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Materials builder started")
        self.logger.info("Allowed task types: {}".format(self.allowed_tasks))

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp for update operation
        self.timestamp = datetime.utcnow()

        # Get all processed tasks:
        q = dict(self.query)
        q["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = set(self.tasks.distinct("task_id", q))
        processed_tasks = set(self.materials.distinct("task_ids"))
        to_process_tasks = all_tasks - processed_tasks
        to_process_forms = self.tasks.distinct("formula_pretty", {"task_id": {"$in": list(to_process_tasks)}})
        self.logger.info("Found {} unprocessed tasks".format(len(to_process_tasks)))
        self.logger.info("Found {} unprocessed formulas".format(len(to_process_forms)))

        # Tasks that have been updated since we last viewed them
        update_q = dict(q)
        update_q.update(self.tasks.lu_filter(self.materials))
        updated_forms = self.tasks.distinct("formula_pretty", update_q)
        self.logger.info("Found {} updated systems to proces".format(len(updated_forms)))

        forms_to_update = set(updated_forms) | set(to_process_forms)
        self.logger.info("Processing {} total systems".format(len(forms_to_update)))
        self.total = len(forms_to_update)

        for formula in forms_to_update:
            tasks_q = dict(q)
            tasks_q["formula_pretty"] = formula
            tasks = list(self.tasks.query(criteria=tasks_q))
            yield tasks

    def process_item(self, tasks):
        """
        Process the tasks into a list of materials

        Args:
            tasks [dict] : a list of task docs

        Returns:
            ([dict],list) : a list of new materials docs and a list of task_ids that were processsed
        """

        formula = tasks[0]["formula_pretty"]
        t_ids = [t["task_id"] for t in tasks]
        self.logger.debug("Processing {} : {}".format(formula, t_ids))

        materials = []
        grouped_tasks = self.filter_and_group_tasks(tasks)

        for group in grouped_tasks:
            materials.append(self.make_mat(group))

        self.logger.debug("Produced {} materials for {}".format(len(materials), tasks[0]["formula_pretty"]))

        return materials

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """

        items = [i for i in filter(None, chain.from_iterable(items)) if self.valid(i)]

        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info("Updating {} materials".format(len(items)))
            self.materials.update(docs=items, update_lu=False)
        else:
            self.logger.info("No items to update")

    def make_mat(self, task_group):
        """
        Converts a group of tasks into one material
        """

        # Convert the task to properties and flatten
        all_props = list(chain.from_iterable([self.task_to_prop_list(t) for t in task_group]))

        if self.require_structure_opt:
            # Only consider structure optimization task_ids for material task_id
            possible_mat_ids = [prop for prop in all_props if "Structure Optimization" in prop["task_type"]]
        else:
            possible_mat_ids = all_props

        # Sort task_ids by ID
        possible_mat_ids = [prop[self.tasks.key] for prop in sorted(possible_mat_ids, key=lambda x: ID_to_int(x["task_id"]))]

        # If we don"t have a structure optimization then just return no material
        if len(possible_mat_ids) == 0:
            return None
        else:
            mat_id = possible_mat_ids[0]

        # Sort and group based on materials key
        sorted_props = sorted(all_props, key=lambda x: x["materials_key"])
        grouped_props = groupby(sorted_props, lambda x: x["materials_key"])

        # Choose the best prop for each materials key: highest quality score and lowest energy calculation
        best_props = []
        for _, props in grouped_props:
            # Sort for highest quality score and lowest energy
            sorted_props = sorted(props, key=lambda x: (x["quality_score"], -1.0 * x["energy"]), reverse=True)
            if sorted_props[0].get("aggregate", False):
                vals = [prop["value"] for prop in sorted_props]
                prop = sorted_props[0]
                prop["value"] = vals
                # Can"t track an aggregated property
                prop["track"] = False
                best_props.append(prop)
            else:
                best_props.append(sorted_props[0])

        # Add in the provenance for the properties
        origins = [{k: prop[k]
                    for k in ["materials_key", "task_type", "task_id", "last_updated"]} for prop in best_props
                   if prop.get("track", False)]

        # Store all the task_ids
        task_ids = list(set([t["task_id"] for t in task_group]))

        # Store task_types
        task_types = {t["task_id"]: t["task_type"] for t in all_props}

        mat = {
            self.materials.lu_field: max([prop["last_updated"] for prop in all_props]),
            "created_at": min([prop["last_updated"] for prop in all_props]),
            "task_ids": task_ids,
            self.materials.key: mat_id,
            "origins": origins,
            "task_types": task_types
        }

        for prop in best_props:
            set_(mat, prop["materials_key"], prop["value"])

        # Add metadata back into document and convert back to conventional standard
        if "structure" in mat:
            structure = Structure.from_dict(mat["structure"])
            sga = SpacegroupAnalyzer(structure, symprec=0.1)
            mat["structure"] = structure.as_dict()
            mat.update(structure_metadata(structure))

        return mat

    def filter_and_group_tasks(self, tasks):
        """
        Groups tasks by structure matching
        """

        filtered_tasks = [t for t in tasks if task_type(t["orig_inputs"]) in self.allowed_tasks]

        structures = []

        for idx, t in enumerate(filtered_tasks):
            s = Structure.from_dict(t["output"]["structure"])
            s.index = idx
            total_mag = get(t, "calcs_reversed.0.output.outcar.total_magnetization", 0)
            s.total_magnetization = total_mag if total_mag else 0
            # a fix for very old tasks that did not report site-projected magnetic moments
            # so that we can group them appropriately
            if ('magmom' not in s.site_properties) and (get(t, "input.parameters.ISPIN", 1) == 2) and \
                    has(t, "input.parameters.MAGMOM"):
                # TODO: map input structure sites to output structure sites
                s.add_site_property("magmom", t["input"]["parameters"]["MAGMOM"])
            structures.append(s)

        grouped_structures = group_structures(
            structures,
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
            separate_mag_orderings=self.separate_mag_orderings)

        for group in grouped_structures:
            yield [filtered_tasks[struc.index] for struc in group]

    def task_to_prop_list(self, task):
        """
        Converts a task into an list of properties with associated metadata
        """
        t_type = task_type(task["orig_inputs"])
        t_id = task["task_id"]

        # Convert the task doc into a serious of properties in the materials
        # doc with the right document structure
        props = []
        for prop in self.__settings:
            if t_type in prop["quality_score"].keys():
                if has(task, prop["tasks_key"]):
                    props.append({
                        "value": get(task, prop["tasks_key"]),
                        "task_type": t_type,
                        "task_id": t_id,
                        "quality_score": prop["quality_score"][t_type],
                        "track": prop.get("track", False),
                        "aggregate": prop.get("aggregate", False),
                        "last_updated": task[self.tasks.lu_field],
                        "energy": get(task, "output.energy", 0.0),
                        "materials_key": prop["materials_key"]
                    })
                elif not prop.get("optional", False):
                    self.logger.error("Failed getting {} for task: {}".format(prop["tasks_key"], t_id))
        return props

    def valid(self, doc):
        """
        Determines if the resulting material document is valid
        """
        return "structure" in doc

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Basic search index for tasks
        self.tasks.ensure_index(self.tasks.key, unique=True)
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")
        self.tasks.ensure_index(self.tasks.lu_field)

        # Search index for materials
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index("task_ids")
        self.materials.ensure_index(self.materials.lu_field)


def structure_metadata(structure):
    """
    Generates metadata based on a structure
    """
    comp = structure.composition
    elsyms = sorted(set([e.symbol for e in comp.elements]))
    meta = {
        "nsites": structure.num_sites,
        "elements": elsyms,
        "nelements": len(elsyms),
        "composition": comp.as_dict(),
        "composition_reduced": comp.reduced_composition.as_dict(),
        "formula_pretty": comp.reduced_formula,
        "formula_anonymous": comp.anonymized_formula,
        "chemsys": "-".join(elsyms),
        "volume": structure.volume,
        "density": structure.density,
    }

    return meta


def group_structures(structures, ltol=0.2, stol=0.3, angle_tol=5, symprec=0.1, separate_mag_orderings=False):
    """
    Groups structures according to space group and structure matching

    Args:
        structures ([Structure]): list of structures to group
        ltol (float): StructureMatcher tuning parameter for matching tasks to materials
        stol (float): StructureMatcher tuning parameter for matching tasks to materials
        angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
        symprec (float): symmetry tolerance for space group finding
        separate_mag_orderings (bool): Separate magnetic orderings into different materials
    """

    sm = StructureMatcher(
        ltol=ltol,
        stol=stol,
        angle_tol=angle_tol,
        primitive_cell=True,
        scale=True,
        attempt_supercell=False,
        allow_subset=False,
        comparator=ElementComparator())

    def get_sg(struc):
        # helper function to get spacegroup with a loose tolerance
        try:
            sg = struc.get_space_group_info(symprec=symprec)[1]
        except:
            sg = -1

        return sg

    def get_mag_ordering(struc):
        # helperd function to get a label of the magnetic ordering type
        return np.around(np.abs(struc.total_magnetization) / struc.volume, decimals=1)

    # First group by spacegroup number then by structure matching
    for sg, pregroup in groupby(sorted(structures, key=get_sg), key=get_sg):
        for group in sm.group_structures(list(pregroup)):

            # Match magnetic orderings here
            if separate_mag_orderings:
                for _, mag_group in groupby(sorted(group, key=get_mag_ordering), key=get_mag_ordering):
                    yield list(mag_group)
            else:
                yield group


def ID_to_int(s_id):
    """
    Converts a string id to tuple
    falls back to assuming ID is an Int if it can't process
    Assumes string IDs are of form "[chars]-[int]" such as mp-234
    """
    if isinstance(s_id, str):
        return (s_id.split("-")[0], int(str(s_id).split("-")[-1]))
    elif isinstance(s_id, (int, float)):
        return s_id
    else:
        raise Exception("Could not parse {} into a number".format(s_id))
