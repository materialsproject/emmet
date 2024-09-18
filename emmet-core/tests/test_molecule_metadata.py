import pytest
from pymatgen.core import Molecule
from pymatgen.core.composition import Composition
from pymatgen.core.periodic_table import Element

from emmet.core.structure import MoleculeMetadata


@pytest.fixture()
def molecule():
    return Molecule(species=["O", "O"], coords=[[0, 0, 0], [0.0, 0.0, 1.16]])


def test_from_molecule(molecule):
    metadata = MoleculeMetadata.from_molecule(molecule, extra_field="extra_value")
    assert metadata.natoms == 2
    assert metadata.elements == [Element("O")]
    assert metadata.nelements == 1
    assert metadata.composition == Composition("O2")
    assert metadata.composition_reduced == Composition("O2").reduced_composition
    assert metadata.formula_alphabetical == "O2"
    assert metadata.formula_pretty == "O2"
    assert metadata.formula_anonymous == "A"
    assert metadata.chemsys == "O"
    assert metadata.symmetry.point_group == "D*h"
    assert metadata.charge == 0
    assert metadata.spin_multiplicity == 1
    assert metadata.nelectrons == 16

    assert metadata.model_config.get("extra") is None, (
        "Should not allow extra field to keep validation strict, if "
        "extra fields are needed, set extra='allow' on a subclass"
    )
    assert metadata.model_dump().get("extra_field") is None


def test_from_comp(molecule):
    metadata = MoleculeMetadata.from_composition(molecule.composition)
    assert metadata.elements == [Element("O")]
    assert metadata.nelements == 1
    assert metadata.composition == Composition("O2")
    assert metadata.composition_reduced == Composition("O2").reduced_composition
    assert metadata.formula_pretty == "O2"
    assert metadata.formula_anonymous == "A"
    assert metadata.chemsys == "O"
