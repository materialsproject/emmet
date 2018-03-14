from datetime import datetime
from itertools import chain, groupby
import os

from monty.serialization import loadfn
from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from maggma.builder import Builder
from emmet.vasp.task_tagger import task_type
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
                 separate_mag_orderings=True,
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
        """

        self.tasks = tasks
        self.materials_settings = materials_settings if materials_settings else default_mat_settings
        self.materials = materials
        self.mat_prefix = mat_prefix
        self.query = query if query else {}
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.separate_mag_orderings = separate_mag_orderings

        self.__settings = loadfn(self.materials_settings)

        self.allowed_tasks = {t_type for d in self.__settings for t_type in d['quality_score']}

        super().__init__(sources=[tasks], targets=[materials], **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Materials Builder Started")
        self.logger.info("Allowed Task Types: {}".format(self.allowed_tasks))

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp for update operation
        self.time_stamp = datetime.utcnow()

        # Get all processed tasks:
        q = dict(self.query)
        q["state"] = "successful"

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

    def make_mat(self, task_group):
        """
        Converts a group of tasks into one material
        """
        all_props = list(chain.from_iterable([self.task_to_prop_list(t) for t in task_group]))
        sorted_props = sorted(all_props, key=lambda x: x['materials_key'])
        grouped_props = groupby(sorted_props, lambda x: x['materials_key'])
        best_props = []
        for name, prop in grouped_props:

            sorted_props = sorted(prop, key=lambda x: x['quality_score'], reverse=True)
            best_props.append(sorted_props[0])

        # Add in the provenance for the properties
        origins = [{k: prop[k]
                    for k in ["materials_key", "task_type", "task_id", "last_updated"]}
                   for prop in best_props
                   if prop.get("track", False)]

        task_ids = list(sorted([t["task_id"] for t in task_group], key=lambda x: int(str(x).split("-")[-1])))

        task_types = {t["task_id"]: t["task_type"] for t in all_props}

        mat = {
            "updated_at": datetime.utcnow(),
            "task_ids": task_ids,
            self.materials.key: task_ids[0],
            "origins": origins,
            "task_types": task_types
        }

        for prop in best_props:
            set_(mat, prop["materials_key"], prop["value"])

        return mat

    def filter_and_group_tasks(self, tasks):
        """
        Groups tasks by structure matching
        """

        filtered_tasks = [t for t in tasks if task_type(t['orig_inputs']) in self.allowed_tasks]

        structures = []

        for idx, t in enumerate(filtered_tasks):
            s = Structure.from_dict(t["output"]['structure'])
            s.index = idx
            structures.append(s)

        if self.separate_mag_orderings:
            for structure in structures:
                if has(structure.site_properties, "magmom"):
                    structure.add_spin_by_site(structure.site_properties['magmom'])
                    structure.remove_site_property('magmom')

        sm = StructureMatcher(
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
            primitive_cell=True,
            scale=True,
            attempt_supercell=False,
            allow_subset=False,
            comparator=ElementComparator())

        grouped_structures = sm.group_structures(structures)

        grouped_tasks = [[filtered_tasks[struc.index] for struc in group] for group in grouped_structures]

        return grouped_tasks

    def task_to_prop_list(self, task):
        """
        Converts a task into an list of properties
        """
        t_type = task_type(task['orig_inputs'])
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
                        "last_updated": task["last_updated"],
                        "materials_key": prop["materials_key"]
                    })
                elif not prop.get("optional", False):
                    self.logger.error("Failed getting {} for task: {}".format(prop["tasks_key"], t_id))
        return props

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        items = [i for i in filter(None, chain.from_iterable(items)) if self.valid(i)]
        if len(items) > 0:
            self.logger.info("Updating {} materials".format(len(items)))
            self.materials.update(docs=items)
        else:
            self.logger.info("No items to update")

    def valid(self, doc):
        """
        Determines if the resulting material document is valid
        """
        return "structure" in doc

    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections
        :return:
        """

        # Basic search index for tasks
        self.tasks.ensure_index("task_id", unique=True)
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")
        self.tasks.ensure_index(self.tasks.lu_field)

        # Search index for materials
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index("task_ids")
