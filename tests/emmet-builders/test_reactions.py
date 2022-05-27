import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.jaguar.pes import PESMinimumBuilder, TransitionStateBuilder
from emmet.builders.jaguar.reaction import ReactionAssociationBuilder, ReactionBuilder


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "jaguar" / "c3h3o2_tasks.json.gz", key="calcid")


@pytest.fixture(scope="session")
def minima_store():
    return MemoryStore(key="molecule_id")


@pytest.fixture(scope="session")
def ts_store():
    return MemoryStore(key="molecule_id")

@pytest.fixture(scope="session")
def assoc_store():
    return MemoryStore(key="reaction_id")

@pytest.fixture(scope="session")
def reaction_store():
    return MemoryStore(key="reaction_id")


def test_pes_builders(tasks_store, minima_store, ts_store, assoc_store, reaction_store):
    min_builder = PESMinimumBuilder(tasks=tasks_store,
                                    minima=minima_store)
    min_builder.run()

    ts_builder = TransitionStateBuilder(tasks=tasks_store,
                                        transition_states=ts_store)
    ts_builder.run()

    assoc_builder = ReactionAssociationBuilder(minima=minima_store,
                                               transition_states=ts_store,
                                               assoc=assoc_store)
    assoc_builder.run()
    assert assoc_store.count() == 6

    rxn_builder = ReactionBuilder(assoc=assoc_store,
                                  reactions=reaction_store)
    rxn_builder.run()
    assert reaction_store.count() == 2