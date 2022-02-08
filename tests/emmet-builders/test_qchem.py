import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "C3H4Li1O3.json.gz")


@pytest.fixture(scope="session")
def assoc_store():
    return MemoryStore()


def test_validator(tasks_store, assoc_store):
    builder = MoleculesAssociationBuilder(tasks=tasks_store, assoc=assoc_store)
    builder.run()
    assert assoc_store.count() == 67
    assert assoc_store.count({"deprecated": True}) == 1