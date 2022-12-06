import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder, MoleculesBuilder
from emmet.builders.molecules.atomic import PartialChargesBuilder, PartialSpinsBuilder


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "C3H4Li1O3.json.gz")


@pytest.fixture(scope="session")
def mol_store(tasks_store):
    assoc_store = MemoryStore(key="molecule_id")
    stage_one = MoleculesAssociationBuilder(tasks=tasks_store, assoc=assoc_store)
    stage_one.run()

    mol_store = MemoryStore(key="molecule_id")
    stage_two = MoleculesBuilder(assoc=assoc_store, molecules=mol_store, prefix="libe")
    stage_two.run()

    return mol_store


@pytest.fixture(scope="session")
def charges_store():
    return MemoryStore()


@pytest.fixture(scope="session")
def spins_store():
    return MemoryStore()

@pytest.mark.skip(reason="Waiting on molecule update.")
def test_charges_builder(tasks_store, mol_store, charges_store):
    builder = PartialChargesBuilder(
        tasks_store, mol_store, charges_store, methods=["mulliken", "resp", "critic2"]
    )
    builder.run()

    assert charges_store.count() == 138
    assert charges_store.count({"deprecated": True}) == 0

@pytest.mark.skip(reason="Waiting on molecule update.")
def test_spins_builder(tasks_store, mol_store, spins_store):
    builder = PartialSpinsBuilder(
        tasks_store, mol_store, spins_store, methods=["mulliken"]
    )
    builder.run()

    assert spins_store.count() == 18
    assert spins_store.count({"deprecated": True}) == 0
