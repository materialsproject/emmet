import os
from datetime import datetime
from pymongo import ReturnDocument

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from emmet.vasp.builders.task_tagger import TaskTagger

from maggma.builders import Builder

__author__ = "Anubhav Jain<ajain@lbl.gov>, Shyam Dwaraknath <shyamd@lbl.gov>"


class MaterialsBuilder(Builder):
    def __init__(self, tasks, materials_settings, materials, snls=None, query={}, only_snls=False):
        """
        Creates a materials collection from tasks and tags
        
        Args:
            tasks (Store): Store of task documents
            materials_settings (Store): settings for building the material document
            materials (Store): Store of materials documents to generate
            snls (Store): Store of SNLs to match materials to
            query (dict): dictionary to limit tasks to be analyzed
            only_snls (bool): only make materials that have a SNL in the snl Store
        """

        self.tasks = tasks
        self.__settings = list(materials_settings.find())
        self.materials = materials
        self.query = query
        self.snls = snls

        self.query.update(self.materials.)

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
                                                 {"$project": {"task_id": 1, "formula_reduced_abc": 1}},
                                                 {"$group": {"_id": {"formula_reduced_abc": "$formula_reduced_abc"},
                                                             "task_ids": {"$addToSet": "$task_id"}}}
                                                 ])

        for formula, task_ids in formulas_reduced.items():
            # Find the materials with reduced formula
            # return all tasks and materials
            tasks_q = dict(q)
            tasks_q['task_id'] = {"$in": task_ids}
            tasks = list[self.tasks.find(tasks_q)]

            mats_q = dict(q)
            mats_q['formula_reduced_abc'] = formula
            mats = list[self.materials.find(mats_q)]

            yield tasks,mats

    def process_item(self, item):
        """
        Find the task_type for the item 

        Args:
            item ((dict,[dict])): a task doc and a list of possible tag definitions
        """

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([dict]): task_type dicts to insert into task_types collection
        """

    def finalize(self):
        pass
