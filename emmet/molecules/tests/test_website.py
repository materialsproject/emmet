import unittest
import os
from maggma.stores import JSONStore, MemoryStore, MongoStore
from emmet.qchem.molecules import MoleculesBuilder
from emmet.molecules.redox import RedoxBuilder
from emmet.molecules.website import WebsiteMoleculesBuilder

__author__ = "Sam Blau"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "sample_qchem_tasks.json")


class TestWebsite(unittest.TestCase):
    def setUp(self):
        tasks = JSONStore(test_tasks)
        molecules = MemoryStore(name="molecules")
        redox = MemoryStore(name="redox")
        self.website = MemoryStore(name="redox")
        tasks.connect()
        molecules.connect()
        redox.connect()
        self.website.connect()
        mbuilder = MoleculesBuilder(tasks, molecules)
        for group in list(mbuilder.get_items()):
            mbuilder.update_targets([mbuilder.process_item(group)])
        rbuilder = RedoxBuilder(molecules,redox)
        for group in list(rbuilder.get_items()):
            rbuilder.update_targets([rbuilder.process_item(group)])
        self.wbuilder = WebsiteMoleculesBuilder(molecules,redox,self.website)

    def test_get_and_process(self):
        items = list(self.wbuilder.get_items())
        self.assertEqual(len(items),9)
        for item in items:
            mol = self.wbuilder.process_item(item)
            keys = ['_id',
                    'run_tags',
                    'charge',
                    'spin_multiplicity',
                    'electrode_potentials',
                    'molecule',
                    'xyz',
                    'smiles',
                    'can',
                    'inchi',
                    'inchi_root',
                    'svg',
                    'pointgroup',
                    'elements',
                    'nelements',
                    'formula',
                    'pretty_formula',
                    'reduced_cell_formula_abc',
                    'implicit_solvent',
                    'MW',
                    'user_tags',
                    'snl_final',
                    'snlgroup_id_final',
                    'task_id_deprecated',
                    'task_id',
                    'sbxn']
            for key in keys:
                self.assertIn(key,mol.keys())
            if "EA" not in mol.keys():
                self.assertIn("IE",mol.keys())
            elif "IE" not in mol.keys():
                self.assertIn("EA",mol.keys())
            else:
                self.assertIn("IE",mol.keys())
                self.assertIn("EA",mol.keys())

    def test_update(self):
        for item in list(self.wbuilder.get_items()):
            self.wbuilder.update_targets([self.wbuilder.process_item(item)])
        self.assertEqual(len(self.website.distinct("task_id")),9)

if __name__ == "__main__":
    unittest.main()
