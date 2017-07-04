import logging
from datetime import datetime

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from maggma.builder import Builder
from emmet.vasp.builders.task_tagger import TaskTagger
from emmet.utils import make_mongolike, recursive_update, get_logger

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class MaterialsBuilder(Builder):
    def __init__(self, tasks, materials_settings, materials, snls=None, query={}, only_snls=False, ltol=0.2, stol=0.3,
                 angle_tol=5, **kwargs):
        """
        Creates a materials collection from tasks and tags
        
        Args:
            tasks (Store): Store of task documents
            materials_settings (Store): settings for building the material document
            materials (Store): Store of materials documents to generate
            snls (Store): Store of SNLs to match materials to
            query (dict): dictionary to limit tasks to be analyzed
            only_snls (bool): only make materials that have a SNL in the snl Store
            ltol (float): StructureMatcher tuning parameter for matching tasks to materials
            stol (float): StructureMatcher tuning parameter for matching tasks to materials
            angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
        """

        self.tasks = tasks
        self.__settings = list(materials_settings().find())
        self.materials_settings = materials_settings
        self.materials = materials
        self.query = query
        self.snls = snls
        self.only_snls = only_snls
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol

        self.logger = logging.getLogger(__name__).addHandler(logging.NullHandler())

        super().__init__(sources=[tasks, materials_settings, snls] if snls else [tasks, materials_settings],
                         targets=[materials],
                         **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents
        
        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Materials Builder Started")

        # Get only successfull tasks
        q = dict(self.query)
        q["state"] = "successful"

        # only consider tasks that have been updated since materials was last updated
        q.update(self.tasks.lu_filter(self.materials))

        # MongoDB aggregation to find and group all successfull tasks by formula_pretty
        formulas_reduced = self.tasks().aggregate([{"$match": q},
                                                   {"$project": {"task_id": 1, "formula_pretty": 1}},
                                                   {"$group": {"_id": {"formula_pretty": "$formula_pretty"},
                                                               "task_ids": {"$addToSet": "$task_id"}}}
                                                   ])

        self.logger.info("Found {} unique formulas that need updating".format(formulas_reduced.count()))

        for doc in formulas_reduced:
            formula = doc["_id"]['formula_pretty']
            task_ids = set(doc['task_ids'])
            logger.debug("Processing {} : {}".format(formula, task_ids))

            tasks_q = dict(q)
            tasks_q["task_id"] = {"$in": list(task_ids)}
            tasks = list(self.tasks().find(tasks_q))

            mats_q = dict(q)
            mats_q["formula_pretty"] = formula
            mats = list(self.materials().find(mats_q))

            # return all matching materials and tasks for this formula
            yield tasks, mats

    def process_item(self, item):
        """
        Process the tasks and materials into just a list of materials

        Args:
            item ((dict,[dict])): a task doc and a list of possible tag definitions
            
        Returns:
            ([dict],list) : a list of new materials docs and a list of task_ids that were processsed  
        """

        tasks = item[0]
        materials = item[1]

        for t in sorted(tasks, key=lambda x: x['task_id']):
            mat = self.match(t, materials)

            if mat:
                self.update_mat(t, mat)
            else:
                materials.append(self.new_mat(t))

        t_ids = [t['task_id'] for t in tasks]

        return materials, t_ids

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
        Generates a new material doc from the task
        
        Args:
            task (dict): the task doc
            
        Returns:
            dict: a materials doc
        
        """
        t_type = TaskTagger.task_type(task)
        t_id = task['task_id']

        # Convert the task doc into a serious of properties in the materials doc with the right document structure
        props = [make_mongolike(task, prop['tasks_key'], prop['materials_key']) for prop in self.__settings if
                 t_type in prop['quality_score'].keys()]

        # Add in the provenance for the properties
        origins = [{"materials_key": prop["materials_key"],
                    "task_type": t_type,
                    "task_id": t_id,
                    "updated_at": datetime.utcnow()} for prop in self.__settings if
                   t_type in prop['quality_score'].keys() and len(prop['quality_score'].keys()) > 1]

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
                if doc['materials_key'] is prop['materials_key']:
                    return doc
            return {}

        t_type = TaskTagger.task_type(task)
        t_id = task['task_id']

        props = []

        for prop in self.__settings:
            # If this task type is considered for this property
            if t_type in prop['quality_score'].keys():

                # Get the property score
                t_score = prop['quality_score'][t_type]

                # Get the origin data for the property in the materials doc
                prop_doc = get_origin(mat['origins'], prop)
                m_type = prop_doc.get('task_type', "")
                m_score = prop_doc.get('quality_score', {}).get(m_type, 0)

                # if the task property is of a higher quality than the material property
                # greater than or equal is used to allow for multiple calculations of the same type
                # assuming successive calculations are 'better'
                if t_score >= m_score:
                    # Build the property into a document with the right structure and save it
                    props.append(make_mongolike(task, prop['tasks_key'], prop['materials_key']))
                    if len(prop['quality_score'].keys()) > 1:
                        prop_doc.update({"task_type": t_type,
                                         "task_id": t_id,
                                         "updated_at": datetime.utcnow()})

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

        self.logger.info("Updating {} materials documents".format(len(items[0])))

        for m_list, t_ids in items:
            for m in m_list:
                if len(set(m["task_ids"]).intersection(t_ids)) > 0:
                    # Update the last updated field
                    m[self.materials.lu_field] = datetime.utcnow()
                    self.materials().replace_one({"material_id": m['material_id']}, m, upsert=True)

                    # TODO: Add in SNL checking here

    def finalize(self):
        pass
