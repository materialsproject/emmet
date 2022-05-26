import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.core.jaguar.task import TaskDocument
from emmet.builders.jaguar.pes import PESMinimumBuilder, TransitionStateBuilder


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "jaguar" / "c3h3o2_tasks.json.gz", key="calcid")


@pytest.fixture(scope="session")
def minima_store():
    return MemoryStore()


@pytest.fixture(scope="session")
def ts_store():
    return MemoryStore()


def test_pes_builders(tasks_store, minima_store, ts_store):
    min_builder = PESMinimumBuilder(tasks=tasks_store,
                                    minima=minima_store)
    min_builder.run()
    assert minima_store.count() == 43
    assert minima_store.count({"deprecated": True}) == 1

    ts_builder = TransitionStateBuilder(tasks=tasks_store,
                                        transition_states=ts_store)
    ts_builder.run()
    assert ts_store.count() == 36
    assert ts_store.count({"deprecated": True}) == 0