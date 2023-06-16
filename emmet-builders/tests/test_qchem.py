import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder, MoleculesBuilder


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "C2H4.json.gz")


@pytest.fixture(scope="session")
def assoc_store():
    return MemoryStore()


@pytest.fixture(scope="session")
def mol_store():
    return MemoryStore()


def test_molecules_builder(tasks_store, assoc_store, mol_store):
    stage_one = MoleculesAssociationBuilder(tasks=tasks_store, assoc=assoc_store)
    stage_one.run()
    assert assoc_store.count() == 76
    assert assoc_store.count({"deprecated": True}) == 9

    assoc_store.key = "molecule_id"

    stage_two = MoleculesBuilder(assoc=assoc_store, molecules=mol_store)
    stage_two.run()

    assert mol_store.count() == 8
    assert mol_store.count({"deprecated": True}) == 0
