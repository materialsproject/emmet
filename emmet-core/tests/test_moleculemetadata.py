from pymatgen.core import Molecule
from pymatgen.core.composition import Composition
from pymatgen.core.periodic_table import Element

from emmet.core.structure import MoleculeMetadata

molecule = Molecule(
    species=["Mg", "O"],
    coords=[[0, 0, 0], [0.5, 0.5, 0.5]],
)


def test_from_molecule():
    metadata = MoleculeMetadata.from_molecule(molecule).dict()
    assert metadata["natoms"] == 2
    assert metadata["elements"] == [Element("Mg"), Element("O")]
    assert metadata["nelements"] == 2
    assert metadata["composition"] == Composition("MgO")
    assert metadata["composition_reduced"] == Composition("MgO").reduced_composition
    assert metadata["formula_alphabetical"] == Composition("MgO").alphabetical_formula
    assert metadata["formula_anonymous"] == Composition("MgO").anonymized_formula
    assert metadata["chemsys"] == Composition("MgO").chemsys
    assert metadata["point_group"] == "C*v"
    assert metadata["charge"] == 0
    assert metadata["spin_multiplicity"] == 1
    assert metadata["nelectrons"] == 20


def test_from_comp():
    metadata = MoleculeMetadata.from_composition(molecule.composition).dict()
    assert metadata["elements"] == [Element("Mg"), Element("O")]
    assert metadata["nelements"] == 2
    assert metadata["composition"] == Composition("MgO")
    assert metadata["composition_reduced"] == Composition("MgO").reduced_composition
    assert metadata["formula_alphabetical"] == Composition("MgO").alphabetical_formula
    assert metadata["formula_anonymous"] == Composition("MgO").anonymized_formula
    assert metadata["chemsys"] == Composition("MgO").chemsys
