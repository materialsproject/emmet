import pytest
from pymatgen.core import Molecule
from pymatgen.core.composition import Composition
from pymatgen.core.periodic_table import Element

from emmet.core.structure import MoleculeMetadata


@pytest.fixture
def molecule():
    test_mol = Molecule(
        species=["Mg", "O"],
        coords=[[0, 0, 0], [0.5, 0.5, 0.5]],
    )
    return test_mol


def test_from_molecule(molecule):
    metadata = MoleculeMetadata.from_molecule(molecule)
    assert metadata.natoms == 2
    assert metadata.elements == [Element("Mg"), Element("O")]
    assert metadata.nelements == 2
    assert metadata.composition == Composition("MgO")
    assert metadata.composition_reduced == Composition("MgO").reduced_composition
    assert metadata.formula_alphabetical == "Mg1 O1"
    assert metadata.formula_pretty == "MgO"
    assert metadata.formula_anonymous == "AB"
    assert metadata.chemsys == "Mg-O"
    assert metadata.symmetry.point_group == "C*v"
    assert metadata.charge == 0
    assert metadata.spin_multiplicity == 1
    assert metadata.nelectrons == 20


def test_from_comp(molecule):
    metadata = MoleculeMetadata.from_composition(molecule.composition)
    assert metadata.elements == [Element("Mg"), Element("O")]
    assert metadata.nelements == 2
    assert metadata.composition == Composition("MgO")
    assert metadata.composition_reduced == Composition("MgO").reduced_composition
    assert metadata.formula_pretty == "MgO"
    assert metadata.formula_anonymous == "AB"
    assert metadata.chemsys == "Mg-O"
