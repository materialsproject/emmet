import unittest
import os
import glob
import logging
from bson.json_util import loads
from itertools import chain
from monty.io import zopen
from atomate.vasp.database import VaspCalcDb

from maggma.stores import MongoStore, JSONStore
from maggma.runner import Runner
from emmet.vasp.builders.materials import MaterialsBuilder
from emmet.vasp.builders.thermo import ThermoBuilder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_dir = os.path.join(module_dir, "..", "..", "..",
                        "..", "test_files", "vasp", "builders")


class TestThermo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.tasks = MongoStore("emmet_test", "tasks", lu_field="last_updated")
        cls.tasks.connect()
        cleardb(cls.tasks.collection.database)

        vaspdb = VaspCalcDb(database="emmet_test")
        tasks_dir = os.path.join(test_dir, "tasks")
        
        raw_tasks = JSONStore(glob.glob(os.path.join(test_dir,"tasks","*.json.gz")))
        raw_tasks.connect()
        for task in raw_tasks.query():
            vaspdb.insert_task(task, parse_dos=True, parse_bs=True)

        cls.materials = MongoStore("emmet_test", "materials")

        cls.tasks.connect()
        cls.materials.connect()

        cls.mbuilder = MaterialsBuilder(
            cls.tasks, cls.materials, mat_prefix="", chunk_size=1)

        cls.thermo = MongoStore("emmet_test", "thermo")

        cls.thermo.connect()

        cls.tbuilder = ThermoBuilder(cls.materials, cls.thermo, chunk_size=1)

        runner = Runner([cls.mbuilder])
        runner.run()

    def test_get_entries(self):

        self.assertEqual(len(self.tbuilder.get_entries("Sr")), 6)
        self.assertEqual(len(self.tbuilder.get_entries("Hf")), 4)
        self.assertEqual(len(self.tbuilder.get_entries("O")), 5)
        self.assertEqual(len(self.tbuilder.get_entries("Hf-O-Sr")), 42)
        self.assertEqual(len(self.tbuilder.get_entries("Sr-Hf")), 10)

    def test_get_items(self):
        self.thermo.collection.drop()

        comp_systems = list(self.tbuilder.get_items())
        self.assertEqual(len(comp_systems), 1)
        self.assertEqual(len(comp_systems[0]), 42)

    def test_process_item(self):

        tbuilder = ThermoBuilder(self.materials,self.thermo,query={"elements": ["Sr"]},chunk_size=1)
        entries = list(tbuilder.get_items())[0]
        self.assertEqual(len(entries),6)

        t_docs = self.tbuilder.process_item(entries)
        e_above_hulls = [t['thermo']['e_above_hull'] for t in t_docs]
        sorted_t_docs = list(sorted(t_docs,key=lambda x:x['thermo']['e_above_hull']))
        self.assertEqual(sorted_t_docs[0]['material_id'],"mp-76")

    def test_update_targets(self):
        self.thermo.collection.drop()

        tbuilder = ThermoBuilder(self.materials,self.thermo,query={"elements": ["Sr"]},chunk_size=1)
        entries = list(tbuilder.get_items())[0]
        self.assertEqual(len(entries),6)
        
        t_docs = self.tbuilder.process_item(entries)
        self.tbuilder.update_targets([t_docs])
        self.assertEqual(len(list(self.thermo.query())), len(t_docs))

    @classmethod
    def tearDownClass(self):
        cleardb(self.tasks.collection.database)


def cleardb(db):
    for coll in db.collection_names():
        if coll != "system.indexes":
            db[coll].drop()

if __name__ == "__main__":
    unittest.main()
