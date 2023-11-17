from pymatgen.util.testing import PymatgenTest
from pymatgen.core import Structure

struct_names = (
    "SiO2 Li2O LiFePO4 TlBiSe2 K2O2 Li3V2(PO4)3 Li2O2 CsCl NaFePO4 Pb2TiZrO6 "
    "SrTiO3 TiO2 BaNiO3 VO2".split()
)

test_structures = {
    name.stem: Structure.from_file(name)
    for name in PymatgenTest.TEST_STRUCTURES.keys()
    if name.stem in struct_names
}
