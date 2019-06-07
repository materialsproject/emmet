import unittest
import os
from maggma.stores import JSONStore, MemoryStore, MongoStore
from emmet.qchem.molecules import MoleculesBuilder
from emmet.molecules.redox import RedoxBuilder

__author__ = "Sam Blau"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "sample_qchem_tasks.json")


class TestRedox(unittest.TestCase):
    def setUp(self):
        tasks = JSONStore(test_tasks)
        molecules = MemoryStore(name="molecules")
        self.redox = MemoryStore(name="redox")
        tasks.connect()
        molecules.connect()
        self.redox.connect()
        mbuilder = MoleculesBuilder(tasks, molecules)
        for group in list(mbuilder.get_items()):
            mbuilder.update_targets([mbuilder.process_item(group)])
        self.rbuilder = RedoxBuilder(molecules,self.redox)

    def test_get_and_process(self):
        grouped_mols = list(self.rbuilder.get_items())
        self.assertEqual(len(grouped_mols),5)
        for group in grouped_mols:
            mols = self.rbuilder.process_item(group)
            for mol in mols:
                if mol["formula_alphabetical"] == "C2 H4" or (mol["formula_alphabetical"] == "C6 H8 O2" and mol["charge"] == 1):
                    self.assertEqual("redox" not in mol, True)
                if mol["formula_alphabetical"] == "B1 H4":
                    if mol["charge"] == 0:
                        self.assertEqual(mol["redox"]["reduction"]["solvated"]["Li"],4.512541192925232)
                    elif mol["charge"] == -1:
                        self.assertEqual(mol["redox"]["oxidation"]["solvated"]["Li"],4.512541192925232)
                if mol["formula_alphabetical"] == "C6 H8 O2":
                    if mol["charge"] == 0:
                        self.assertEqual(mol["redox"]["reduction"]["solvated"]["Li"],-0.8944063464772629)
                    elif mol["charge"] == -1:
                        self.assertEqual(mol["redox"]["oxidation"]["solvated"]["Li"],-0.8944063464772629)
                if mol["formula_alphabetical"] == "C2 Cl1 H5":
                    if mol["charge"] == 0:
                        self.assertEqual(mol["redox"]["oxidation"]["solvated"]["Li"],7.011344526755783)
                    elif mol["charge"] == 1:
                        self.assertEqual(mol["redox"]["reduction"]["solvated"]["Li"],7.011344526755783)
                if mol["formula_alphabetical"] == "C2 F1 H1 N4":
                    if mol["charge"] == 0:
                        self.assertEqual(mol["redox"]["oxidation"]["solvated"]["Li"],6.211543683780837)
                        self.assertEqual(mol["redox"]["reduction"]["solvated"]["Li"],2.3044088304573958)
                    elif mol["charge"] == 1:
                        self.assertEqual(mol["redox"]["reduction"]["solvated"]["Li"],6.211543683780837)
                    elif mol["charge"] == -1:
                        self.assertEqual(mol["redox"]["oxidation"]["solvated"]["Li"],2.3044088304573958)

    def test_update(self):
        for group in list(self.rbuilder.get_items()):
            self.rbuilder.update_targets([self.rbuilder.process_item(group)])
        self.assertEqual(len(self.redox.distinct("task_id")),11)

if __name__ == "__main__":
    unittest.main()
