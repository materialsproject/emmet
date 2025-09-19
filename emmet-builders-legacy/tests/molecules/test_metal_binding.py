import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder, MoleculesBuilder
from emmet.builders.molecules.atomic import PartialChargesBuilder, PartialSpinsBuilder
from emmet.builders.molecules.bonds import BondingBuilder
from emmet.builders.molecules.thermo import ThermoBuilder
from emmet.builders.molecules.metal_binding import MetalBindingBuilder


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@pytest.fixture(scope="session")
def tasks(test_dir):
    return JSONStore(test_dir / "lithium_carbonate_tasks.json.gz")


@pytest.fixture(scope="session")
def mols(tasks):
    assoc_store = MemoryStore(key="molecule_id")
    stage_one = MoleculesAssociationBuilder(tasks=tasks, assoc=assoc_store)
    stage_one.run()

    mol_store = MemoryStore(key="molecule_id")
    stage_two = MoleculesBuilder(assoc=assoc_store, molecules=mol_store)
    stage_two.run()

    return mol_store


@pytest.fixture(scope="session")
def charges():
    return MemoryStore()


@pytest.fixture(scope="session")
def spins():
    return MemoryStore()


@pytest.fixture(scope="session")
def bonds():
    return MemoryStore()


@pytest.fixture(scope="session")
def thermo():
    return MemoryStore()


@pytest.fixture(scope="session")
def metal_binding():
    return MemoryStore()


def test_charges_builder(tasks, mols, charges, spins, bonds, metal_binding, thermo):
    charge_build = PartialChargesBuilder(tasks, mols, charges)
    charge_build.run()

    spins_build = PartialSpinsBuilder(tasks, mols, spins)
    spins_build.run()

    bonds_build = BondingBuilder(tasks, mols, bonds)
    bonds_build.run()

    thermo_build = ThermoBuilder(tasks, mols, thermo)
    thermo_build.run()

    metal_binding_build = MetalBindingBuilder(
        mols, charges, spins, bonds, thermo, metal_binding
    )
    metal_binding_build.run()

    assert metal_binding.count() == 6
