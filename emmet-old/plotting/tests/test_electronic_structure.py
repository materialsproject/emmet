import unittest
from unittest.mock import patch, MagicMock
from maggma.stores import MemoryStore
from pymatgen.core.structure import Structure
from pymatgen.core.lattice import Lattice
from emmet.plotting.electronic_structure import ElectronicStructureImageBuilder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TestElectronicStructureImageBuilder(unittest.TestCase):
    def setUp(self):
        coords = list()
        coords.append([0, 0, 0])
        coords.append([0.75, 0.5, 0.75])
        lattice = Lattice(
            [
                [3.8401979337, 0.00, 0.00],
                [1.9200989668, 3.3257101909, 0.00],
                [0.00, -2.2171384943, 3.1355090603],
            ]
        )
        self.structure = Structure(lattice, ["Si", "Si"], coords)

        materials = MemoryStore("materials")
        electronic_structure = MemoryStore("electronic_structure")
        bandstructures = MemoryStore("bandstructure")
        dos = MemoryStore("dos")
        self.builder = ElectronicStructureImageBuilder(
            materials, electronic_structure, bandstructures, dos
        )

    def test_serialization(self):

        doc = self.builder.as_dict()
        builder = ElectronicStructureImageBuilder.from_dict(doc)


if __name__ == "__main__":
    unittest.main()
