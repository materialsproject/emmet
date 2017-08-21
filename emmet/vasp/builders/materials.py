from datetime import datetime
from itertools import chain

from pymongo import ASCENDING, DESCENDING

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from maggma.builder import Builder
from emmet.vasp.builders.task_tagger import TaskTagger
from maggma.utils import get_mongolike, put_mongolike, recursive_update

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class MaterialsBuilder(Builder):
    def __init__(self, tasks, materials_settings, materials, query={}, ltol=0.2, stol=0.3,
                 angle_tol=5, **kwargs):
        """
        Creates a materials collection from tasks and tags

        Args:
            tasks (Store): Store of task documents
            materials_settings (Store): settings for building the material document
            materials (Store): Store of materials documents to generate
            query (dict): dictionary to limit tasks to be analyzed
            ltol (float): StructureMatcher tuning parameter for matching tasks to materials
            stol (float): StructureMatcher tuning parameter for matching tasks to materials
            angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
        """

        self.tasks = tasks
        self.materials_settings = materials_settings
        self.materials = materials
        self.query = query
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol

        self.materials_settings.connect()
        self.__settings = list(self.materials_settings().find())

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

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Get only successfull tasks
        q = dict(self.query)
        q["state"] = "successful"

        # only consider tasks that have been updated since materials was last updated
        q.update(self.tasks.lu_filter(self.materials))

        forms_to_update = self.tasks().find(q).distinct("formula_pretty")
        self.logger.info("Found {} new/updated systems to proces".format(len(forms_to_update)))

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
        t_type = TaskTagger.task_type(task)
        t_id = task["task_id"]

        # Only start new materials with a structure optimization
        if t_type != "structure optimization":
            return None

        # Convert the task doc into a serious of properties in the materials doc with the right document structure
        props = [put_mongolike(prop["materials_key"], get_mongolike(task, prop["tasks_key"])) for prop in
                 self.__settings if
                 t_type in prop["quality_score"].keys()]

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

        t_type = TaskTagger.task_type(task)
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
                            self.logger.error("Failed getting {}".format(e))

        # If there are properties to update
        if len(props) > 0:
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
        self.tasks().create_index([("formula_pretty", DESCENDING),
                                   ("state", ASCENDING),
                                   (self.tasks.lu_field, DESCENDING)], background=True)

        # Search index for materials
        self.materials().create_index("material_id", unique=True, background=True)

    def validate(self):
        pass