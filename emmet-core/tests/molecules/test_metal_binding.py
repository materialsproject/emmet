import pytest

from monty.serialization import loadfn

from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.atomic import PartialChargesDoc, PartialSpinsDoc
from emmet.core.molecules.bonds import MoleculeBondingDoc
from emmet.core.molecules.thermo import MoleculeThermoDoc
from emmet.core.molecules.metal_binding import MetalBindingDoc


@pytest.fixture(scope="session")
def base_mol(test_dir):
    mol = loadfn((test_dir / "metal_binding_doc" / "base_mol_doc.json").as_posix())
    mol_doc = MoleculeDoc(**mol)
    return mol_doc


@pytest.fixture(scope="session")
def base_thermo(test_dir):
    thermo = loadfn((test_dir / "metal_binding_doc" / "thermo.json").as_posix())
    thermo_doc = MoleculeThermoDoc(**thermo)
    return thermo_doc


@pytest.fixture(scope="session")
def charges(test_dir):
    charges = loadfn(
        (test_dir / "metal_binding_doc" / "partial_charges.json").as_posix()
    )
    charges_doc = PartialChargesDoc(**charges)
    return charges_doc


@pytest.fixture(scope="session")
def spins(test_dir):
    spins = loadfn((test_dir / "metal_binding_doc" / "partial_spins.json").as_posix())
    spins_doc = PartialSpinsDoc(**spins)
    return spins_doc


@pytest.fixture(scope="session")
def bonds(test_dir):
    bonds = loadfn((test_dir / "metal_binding_doc" / "bonds.json").as_posix())
    bonds_doc = MoleculeBondingDoc(**bonds)
    return bonds_doc


@pytest.fixture(scope="session")
def metal_thermo(test_dir):
    thermo = loadfn((test_dir / "metal_binding_doc" / "metal_thermo.json").as_posix())
    metal_thermo_doc = MoleculeThermoDoc(**thermo)
    return metal_thermo_doc


@pytest.fixture(scope="session")
def nometal_thermo(test_dir):
    thermo = loadfn((test_dir / "metal_binding_doc" / "nometal_thermo.json").as_posix())
    nometal_thermo_doc = MoleculeThermoDoc(**thermo)
    return nometal_thermo_doc


def test_metal_binding(
    base_mol, charges, spins, bonds, base_thermo, metal_thermo, nometal_thermo
):
    metal_binding = MetalBindingDoc.from_docs(
        method="mulliken-OB-mee",
        metal_indices=[5],
        base_molecule_doc=base_mol,
        partial_charges=charges,
        partial_spins=spins,
        bonding=bonds,
        base_thermo=base_thermo,
        metal_thermo={5: metal_thermo},
        nometal_thermo={5: nometal_thermo},
    )

    assert metal_binding.binding_data[0].metal_index == 5
    assert metal_binding.binding_data[0].metal_element == "Li"

    assert metal_binding.binding_data[0].metal_partial_charge == pytest.approx(
        -0.073376
    )
    assert metal_binding.binding_data[0].metal_assigned_charge == 0
    assert metal_binding.binding_data[0].metal_assigned_spin == 2
    assert metal_binding.binding_data[0].binding_free_energy == pytest.approx(
        1.23790290567376
    )
