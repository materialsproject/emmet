import pytest

from pymatgen.core.periodic_table import Element
from emmet.core.qchem.mol_metadata import MoleculeMetadata
from emmet.stubs import Composition, Molecule


@pytest.fixture
def g2(test_dir):
    g2_mol = Molecule.from_file(test_dir / "molecules" / "diglyme.xyz")
    return g2_mol


def test_constructors(g2):
    g2_from_comp = MoleculeMetadata.from_composition(g2.composition)
    g2_from_mol = MoleculeMetadata.from_molecule(g2, include_molecule=True)

    # nsites
    assert g2_from_comp.nsites is None
    assert g2_from_mol.nsites == 23

    # elements
    assert g2_from_comp.elements == g2_from_mol.elements == [
        Element("C"), Element("H"), Element("O")
    ]
    assert g2_from_comp.nelements == g2_from_mol.nelements == 3

    # composition
    assert g2_from_comp.composition == g2_from_mol.composition == g2.composition

    # molecule
    assert g2_from_comp.molecule is None
    assert g2_from_mol.molecule == g2

    # chemical formula
    assert g2_from_comp.formula_pretty == g2_from_mol.formula_pretty == "H14(C2O)3"
    assert g2_from_comp.formula_alphabetical == g2_from_mol.formula_alphabetical == "C6 H14 O3"
    assert g2_from_comp.formula_anonymous == g2_from_mol.formula_anonymous == "A3B6C14"

    # chemical system
    assert g2_from_comp.chemsys == g2_from_mol.chemsys == "C-H-O"

    # molecular weight
    assert g2_from_comp.molecular_weight == g2_from_mol.molecular_weight == 134.17356

    # SMILES
    assert g2_from_comp.smiles is None and g2_from_comp.canonical_smiles is None
    assert g2_from_mol.smiles == g2_from_mol.canonical_smiles == "COCCOCCOC"

    # InChI
    assert g2_from_comp.inchi is None
    assert g2_from_mol.inchi == "InChI=1S/C6H14O3/c1-7-3-5-9-6-4-8-2/h3-6H2,1-2H3"

    # point group
    assert g2_from_comp.point_group is None
    assert g2_from_mol.point_group == "C1"
