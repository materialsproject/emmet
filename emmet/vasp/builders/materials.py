import os
from datetime import datetime
from pymongo import ReturnDocument

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from emmet.vasp.builders.task_tagger import TaskTagger
from emmet.utils import get_mongolike
from maggma.builders import Builder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class MaterialsBuilder(Builder):
    def __init__(self, tasks, materials_settings, materials, snls=None, query={}, only_snls=False, ltol=0.2, stol=0.3, angle_tol=5):
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
        self.__settings = list(materials_settings.find())
        self.materials = materials
        self.query = query
        self.snls = snls
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol

        # TODO: Add in LU Filter into query

    def get_items(self):
        """
        Gets all items to process into materials documents
        
        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        # Get all successfull task_ids since the last update and group them by reduced_formula
        q = dict(self.query)
        q["state"] = "successful"
        formulas_reduced = self.tasks.aggregate([{"$match": q},
                                                 {"$project": {"task_id": 1, "pretty_formula": 1}},
                                                 {"$group": {"_id": {"pretty_formula": "$pretty_formula"},
                                                             "task_ids": {"$addToSet": "$task_id"}}}
                                                 ])

        for formula, task_ids in formulas_reduced.items():
            # Find the materials with reduced formula
            # return all tasks and materials
            tasks_q = dict(q)
            tasks_q["task_id"] = {"$in": task_ids}
            tasks = list[self.tasks.find(tasks_q)]

            mats_q = dict(q)
            mats_q["pretty_formula"] = formula
            mats = list[self.materials.find(mats_q)]

            yield tasks, mats

    def process_item(self, item):
        """
        Process the tasks and materials 

        Args:
            item ((dict,[dict])): a task doc and a list of possible tag definitions
        """

        tasks = item[0]
        mats = item[1]

        for t in tasks:
            mpid = cls.match(t, mats)
            if mpid:
                m = filter(lambda x: x["material_id"] == mpid, mats)
                self.update_mat(t, m)
            else:
                mats.append(self.new_mat(t))

        return mats

    def match(self, task, mats):
        sm = StructureMatcher(ltol=self.ltol, stol=self.stol, angle_tol=self.angle_tol,
                              primitive_cell=True, scale=True,
                              attempt_supercell=False, allow_subset=False,
                              comparator=ElementComparator())
        t_struct = Structure.from_dict(task["output"]["structure"])

        for m in mats:
            m_struct = Structure.from_dict(m["structure"])
            if task["output"]["spacegroup"]["number"] == m["spacegroup"]["number"] and \
                    sm.fit(m_struct, t_struct):
                return True

        return False

    def new_mat(self, t):
        t_type = TaskTagger.task_type(t)
        t_id = t['task_id']

        # Convert the task doc into a serious of properties in the materials doc with the right structure
        props = [make_mongo_like(t, prop['tasks_key'], prop['materials_key']) for prop in self.__settings if
                 task_type in prop['quality_scores'].keys()]

        # Add in the provenance for the properties
        origin = {prop['materials_key']: {"task_type": t_type,
                                          "task_id": t_id,
                                          "updated_at": datetime.utcnow()} for
                  prop in self.__settings if t_type in prop['quality_score'].keys()}

        d = {"created_at": datetime.utcnow(),
             "updated_at": datetime.utcnow(),
             "task_ids": t_id.
             "material_id": t_id,
             "origins": origin
             }

        for prop in props:
            d.update(prop)

        return d

    def update_mat(self, t, m):
        pass

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([dict]): task_type dicts to insert into task_types collection
        """

    def finalize(self):
        pass
