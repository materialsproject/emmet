import unittest
from unittest.mock import patch, MagicMock
from maggma.stores import MongoStore
from pymatgen.core.structure import Structure
from pymatgen.core.lattice import Lattice
from emmet.vasp.builders.electronic_structure_img import ElectronicStructureImageBuilder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TestElectronicStructureImageBuilder(unittest.TestCase):
    def setUp(self):

        coords = list()
        coords.append([0, 0, 0])
        coords.append([0.75, 0.5, 0.75])
        lattice = Lattice([[3.8401979337, 0.00, 0.00], [1.9200989668, 3.3257101909, 0.00],
                           [0.00, -2.2171384943, 3.1355090603]])
        self.structure = Structure(lattice, ["Si", "Si"], coords)

        materials = MongoStore("emmet_test", "materials")
        electronic_structure = MongoStore("emmet_test", "electronic_structure")

        self.builder = ElectronicStructureImageBuilder(materials, electronic_structure)

    def test_get_bandstructure(self):

        self.builder.bfs = MagicMock()
        mat = {"bandstructure": {"bs_oid": "234234", "bs_compression": "zlib"}}

        with patch("emmet.vasp.builders.electronic_structure_img.json") as json_patch:
            with patch("emmet.vasp.builders.electronic_structure_img.zlib") as zlib_patch:
                self.builder.get_bandstructure(mat)

        self.builder.bfs.get.assert_called()
        json_patch.loads.assert_called()
        zlib_patch.decompress.assert_called()

    def test_get_dos(self):

        self.builder.dfs = MagicMock()
        mat = {"bandstructure": {"dos_oid": "234234", "dos_compression": "zlib"}}

        with patch("emmet.vasp.builders.electronic_structure_img.json") as json_patch:
            with patch("emmet.vasp.builders.electronic_structure_img.zlib") as zlib_patch:
                self.builder.get_dos(mat)

        self.builder.dfs.get.assert_called()
        json_patch.loads.assert_called()
        zlib_patch.decompress.assert_called()


if __name__ == "__main__":
    unittest.main()
