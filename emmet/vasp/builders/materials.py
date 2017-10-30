from datetime import datetime
from itertools import chain
import os

from pymongo import ASCENDING, DESCENDING

from monty.serialization import loadfn
from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from maggma.builder import Builder
from emmet.vasp.builders.task_tagger import task_type
from maggma.utils import get_mongolike, put_mongolike, recursive_update

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
default_mat_settings = os.path.join(module_dir, "materials_settings.json")


class MaterialsBuilder(Builder):
    def __init__(self, tasks, materials, materials_settings = None,query={}, ltol=0.2, stol=0.3,
                 angle_tol=5, **kwargs):
        """
        Creates a materials collection from tasks and tags

        Args:
            tasks (Store): Store of task documents
            materials (Store): Store of materials documents to generate
            materials_settings (Path): Path to settings files
            query (dict): dictionary to limit tasks to be analyzed
            ltol (float): StructureMatcher tuning parameter for matching tasks to materials
            stol (float): StructureMatcher tuning parameter for matching tasks to materials
            angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
        """

        self.tasks = tasks
        self.materials_settings = materials_settings if materials_settings else default_mat_settings
        self.materials = materials
        self.query = query
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol

        self.__settings =loadfn(self.materials_settings)

        self.allowed_tasks = {t_type  for d in self.__settings for t_type in d['quality_score']}

        super().__init__(sources=[tasks],
                         targets=[materials],
                         **kwargs)

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

        # Get all processed tasks:
        q = dict(self.query)
        q["state"] = "successful"
        
        all_tasks = list(self.tasks().find(q).distinct("task_id"))
        processed_tasks = list(self.materials().distinct("task_ids"))
        to_process_tasks = set(all_tasks) - set(processed_tasks)
        to_process_forms = self.tasks().find({"task_id": {"$in": list(to_process_tasks)}}).distinct("formula_pretty")
        self.logger.info("Found {} unprocessed tasks".format(len(to_process_tasks)))


        # Tasks that have been updated since we last viewed them
        update_q = dict(q)
        update_q .update(self.tasks.lu_filter(self.materials))
        updated_forms = self.tasks().find(update_q ).distinct("formula_pretty")
        self.logger.info("Found {} updated systems to proces".format(len(updated_forms)))


        forms_to_update = set(updated_forms) | set(to_process_forms)
        self.logger.info("Processing {} total systems".format(len(forms_to_update)))         

        for formula in forms_to_update:
            tasks_q = dict(q)
            tasks_q["formula_pretty"] = formula
            tasks = list(self.tasks().find(tasks_q))

            yield tasks

    def process_item(self, tasks):
        """
        Process the tasks and materials into just a list of materials

        Args:
            item ((dict,[dict])): a task doc and a list of possible tag definitions

        Returns:
            ([dict],list) : a list of new materials docs and a list of task_ids that were processsed
        """
        materials = []

        formula = tasks[0]["formula_pretty"]
        t_ids = [t["task_id"] for t in tasks]
        self.logger.debug("Processing {} : {}".format(formula, t_ids))

        for t in sorted(tasks, key=lambda x: x["task_id"]):
            mat = self.match(t, materials)

            if mat:
                self.update_mat(t, mat)
            else:
                new_mat = self.new_mat(t)
                if new_mat:
                    materials.append(new_mat)

        self.logger.debug("Produced {} materials for {}".format(len(materials), tasks[0]["formula_pretty"]))

        return materials

    def match(self, task, mats):
        """
        Finds a material doc that matches with the given task

        Args:
            task (dict): the task doc
            mats ([dict]): the materials docs to match against

        Returns:
            dict: a materials doc if one is found otherwise returns None
        """
        sm = StructureMatcher(ltol=self.ltol, stol=self.stol, angle_tol=self.angle_tol,
                              primitive_cell=True, scale=True,
                              attempt_supercell=False, allow_subset=False,
                              comparator=ElementComparator())
        t_struct = Structure.from_dict(task["output"]["structure"])

        for m in mats:
            m_struct = Structure.from_dict(m["structure"])
            if task["output"]["spacegroup"]["number"] == m["spacegroup"]["number"] and \
                    sm.fit(m_struct, t_struct):
                return m

        return None

    def new_mat(self, task):
        """
        Generates a new material doc from a structure optimization task

        Args:
            task (dict): the task doc

        Returns:
            dict: a materials doc

        """
        t_type = task_type(task['input']['incar'])
        t_id = task["task_id"]

        # Only start new materials with a structure optimization
        if "Structure Optimization" not in t_type:
            return None

        # Convert the task doc into a serious of properties in the materials doc with the right document structure
        props = []
        for prop in self.__settings:
            try:
                if t_type in prop["quality_score"].keys():
                    props.append(put_mongolike(prop["materials_key"], get_mongolike(task, prop["tasks_key"])))
            except Exception as e:
                if not prop.get("optional", False):
                    self.logger.error("Failed getting {} for task: {}".format(e,t_id))

        # Add in the provenance for the properties
        origins = [{"materials_key": prop["materials_key"],
                    "task_type": t_type,
                    "task_id": t_id,
                    "last_updated": task["last_updated"]} for prop in self.__settings if
                   t_type in prop["quality_score"].keys() and len(prop["quality_score"].keys()) > 1]

        # Temp document with basic information
        d = {"created_at": datetime.utcnow(),
             "task_ids": [t_id],
             "material_id": t_id,
             "origins": origins
             }

        # Insert the properties into the temp document
        for prop in props:
            recursive_update(d, prop)

        return d

    def update_mat(self, task, mat):
        """
        Updates the materials doc with data from the given task doc

        Args:
            task(dict): the task doc
            mat(dict): the materials doc

        """

        def get_origin(origins, prop):
            for doc in origins:
                if doc["materials_key"] is prop["materials_key"]:
                    return doc
            return {}

        t_type = task_type(task)
        t_id = task["task_id"]

        props = []

        for prop in self.__settings:
            # If this task type is considered for this property
            if t_type in prop["quality_score"].keys():

                # Get the property score
                t_score = prop["quality_score"][t_type]

                # Get the origin data for the property in the materials doc
                prop_doc = get_origin(mat["origins"], prop)
                m_type = prop_doc.get("task_type", "")
                m_score = prop_doc.get("quality_score", {}).get(m_type, 0)

                # if the task property is of a higher quality than the material property
                # greater than or equal is used to allow for multiple calculations of the same type
                # assuming successive calculations are "better"
                if t_score >= m_score:
                    # Build the property into a document with the right structure and save it
                    try:
                        value = get_mongolike(task, prop["tasks_key"])
                        props.append(put_mongolike(prop["materials_key"], value))
                        if len(prop["quality_score"].keys()) > 1:
                            prop_doc.update({"task_type": t_type,
                                             "task_id": t_id,
                                             "last_updated": task["last_updated"]})
                    except Exception as e:
                        if not prop.get("optional", False):
                            self.logger.error("Failed getting {}task: {}".format(e,t_id))

        # Update all props
        for prop in props:
            recursive_update(mat, prop)

        mat["task_ids"].append(t_id)

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        items = list(filter(None, chain(*items)))

        if len(items) > 0:
            self.logger.info("Updating {} materials".format(len(items)))
            bulk = self.materials().initialize_ordered_bulk_op()

            for m in items:
                m[self.materials.lu_field] = datetime.utcnow()
                bulk.find({"material_id": m["material_id"]}).upsert().replace_one(m)
            bulk.execute()
        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections
        :return:
        """

        # Basic search index for tasks
        self.tasks().create_index([("task_id", DESCENDING),
                                   ("state", ASCENDING)], background=True)

        self.tasks().create_index([("task_id", DESCENDING),
                                   ("state", ASCENDING),
                                   ("formula_pretty", DESCENDING),], background=True)

        # Basic updated tasks index for tasks
        self.tasks().create_index([("formula_pretty", DESCENDING),
                                   ("state", ASCENDING),
                                   (self.tasks.lu_field, DESCENDING)], background=True)

        

        # Search index for materials
        self.materials().create_index("material_id", unique=True, background=True)
        self.materials().create_index("task_ids", background=True)
