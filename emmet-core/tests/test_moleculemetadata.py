import pytest

import numpy as np

from pymatgen.core import Molecule
from pymatgen.core.composition import Composition
from pymatgen.core.periodic_table import Element

from emmet.core.structure import MoleculeMetadata


@pytest.fixture
def molecule():
    test_mol = Molecule(
        species=["O", "O"],
        coords=np.asarray([[0, 0, 0], [0.0, 0.0, 1.16]]),
    )
    return test_mol


def test_from_molecule(molecule):
    metadata = MoleculeMetadata.from_molecule(molecule)
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


def test_from_comp(molecule):
    metadata = MoleculeMetadata.from_composition(molecule.composition)
    assert metadata.elements == [Element("O")]
    assert metadata.nelements == 1
    assert metadata.composition == Composition("O2")
    assert metadata.composition_reduced == Composition("O2").reduced_composition
    assert metadata.formula_pretty == "O2"
    assert metadata.formula_anonymous == "A"
    assert metadata.chemsys == "O"
