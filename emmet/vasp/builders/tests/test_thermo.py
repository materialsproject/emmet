import unittest
from itertools import chain
from maggma.stores import MongoStore
from maggma.runner import Runner
from emmet.vasp.builders.tests.test_builders import BuilderTest
from emmet.vasp.builders.materials import MaterialsBuilder
from emmet.vasp.builders.thermo import ThermoBuilder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

class TestThermo(BuilderTest):

    def setUp(self):

        self.materials = MongoStore("emmet_test", "materials")
        self.thermo = MongoStore("emmet_test", "thermo")

        self.materials.connect()
        self.thermo.connect()

        self.mbuilder = MaterialsBuilder(
            self.tasks, self.materials, mat_prefix="", chunk_size=1)
        self.tbuilder = ThermoBuilder(
            self.materials, self.thermo, chunk_size=1)
        runner = Runner([self.mbuilder])
        runner.run()

    def test_get_entries(self):
        self.assertEqual(len(self.tbuilder.get_entries("Sr")), 7)
        self.assertEqual(len(self.tbuilder.get_entries("Hf")), 4)
        self.assertEqual(len(self.tbuilder.get_entries("O")), 6)
        self.assertEqual(len(self.tbuilder.get_entries("Hf-O-Sr")), 44)
        self.assertEqual(len(self.tbuilder.get_entries("Sr-Hf")), 11)

    def test_get_items(self):
        self.thermo.collection.drop()
        comp_systems = list(self.tbuilder.get_items())
        self.assertEqual(len(comp_systems), 1)
        self.assertEqual(len(comp_systems[0]), 44)

    def test_process_item(self):

        tbuilder = ThermoBuilder(self.materials, self.thermo, query={
                                 "elements": ["Sr"]}, chunk_size=1)
        entries = list(tbuilder.get_items())[0]
        self.assertEqual(len(entries), 7)

        t_docs = self.tbuilder.process_item(entries)
        e_above_hulls = [t['thermo']['e_above_hull'] for t in t_docs]
        sorted_t_docs = list(
            sorted(t_docs, key=lambda x: x['thermo']['e_above_hull']))
        self.assertEqual(sorted_t_docs[0]["task_id"], "mp-76")

    def test_update_targets(self):
        self.thermo.collection.drop()

        tbuilder = ThermoBuilder(self.materials, self.thermo, query={
                                 "elements": ["Sr"]}, chunk_size=1)
        entries = list(tbuilder.get_items())[0]
        self.assertEqual(len(entries), 7)

        t_docs = self.tbuilder.process_item(entries)
        self.tbuilder.update_targets([t_docs])
        self.assertEqual(len(list(self.thermo.query())), len(t_docs))

    def tearDown(self):
        self.materials.collection.drop()
        self.thermo.collection.drop()

if __name__ == "__main__":
    unittest.main()
