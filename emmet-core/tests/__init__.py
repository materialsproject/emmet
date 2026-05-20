from emmet.core.io.pymatgen import STRUCTURES_DIR, Structure

struct_names = (
    "SiO2 Li2O LiFePO4 TlBiSe2 K2O2 Li3V2(PO4)3 Li2O2 CsCl NaFePO4 Pb2TiZrO6 "
    "SrTiO3 TiO2 BaNiO3 VO2".split()
)

test_structures = {
    name: Structure.from_file(STRUCTURES_DIR / f"{name}.json") for name in struct_names
}
