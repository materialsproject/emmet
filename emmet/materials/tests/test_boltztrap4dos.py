import os
import unittest
from maggma.stores import JSONStore, MemoryStore
from emmet.materials.boltztrap4dos import Boltztrap4DosBuilder, dos_from_boltztrap

__author__ = "Francesco Ricci"
__email__ = "francesco.ricci@uclouvain.be"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
boltztrap4dos_mat = os.path.join(module_dir, "..", "..", "..", "test_files", "boltztrap4dos_mat.json")
boltztrap4dos_bs = os.path.join(module_dir, "..", "..", "..", "test_files", "boltztrap4dos_bs.json")
boltztrap4dos_dos = os.path.join(module_dir, "..", "..", "..", "test_files", "boltztrap4dos_dos.json")


class TestBoltztrap4DosBuilder(unittest.TestCase):
    def setUp(self):
        self.materials = JSONStore(boltztrap4dos_mat)
        self.materials.connect()
        self.bandstructure = JSONStore(boltztrap4dos_bs)
        self.bandstructure.connect()
        self.dos_ref = JSONStore(boltztrap4dos_dos)
        self.dos_ref.connect()
        self.dos = MemoryStore("dos")
        self.dos.connect()

    @unittest.skipIf("TRAVIS" in os.environ and os.environ["TRAVIS"] == "true", "Skipping this test on Travis CI.")
    def test_process_items(self):
        dosbuilder = Boltztrap4DosBuilder(self.materials, self.bandstructure, self.dos, avoid_projections=True)

        item = self.materials.query_one()
        bs_dict = self.bandstructure.query_one()
        item["bandstructure_uniform"] = bs_dict

        dos = dosbuilder.process_item(item)
        density = dos['densities']['1'][3900]
        self.assertAlmostEqual(density, 5.446126162946311, 5)

    def test_update_targets(self):
        dos = self.dos_ref.query_one()
        items = [dos]

        dosbuilder = Boltztrap4DosBuilder(self.materials, self.bandstructure, self.dos)
        dosbuilder.update_targets(items)

        self.assertListEqual(self.dos.distinct("task_id"), ['mp-663338'])


if __name__ == "__main__":
    unittest.main()
