import os
from datetime import datetime
from pymongo import ReturnDocument

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from maggma.builders import Builder

__author__ = "Anubhav Jain<ajain@lbl.gov>, Shyam Dwaraknath <shyamd@lbl.gov>"

class MaterialsBuilder(Builder):

    def __init__(self, tasks, task_types, materials_settings, materials,query=None):
        """
        Creates a materials collection from tasks and tags
        
        Args:
            tasks (Store): Store of task documents
            tags (Store): Store of tags documents with task_type for each task
            materials_settings (Store): settings for building the material document
            materials (Store): Store of materials documents to generate
            query (dict): dictionary to limit tasks to be analyzed            
        """

        self.tasks = tasks
        self.task_types = task_types
        self.materials_settings = materials_settings
        self.materials = materials
        self.query = query

    def get_items(self):
        """
        Gets all items to process into materials documents
        
        Returns:
            generator or list revelant tasks and materials to process into materials documents
        """

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

