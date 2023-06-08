from __future__ import annotations

import pytest
from emmet.builders.mobility.migration_graph import MigrationGraphBuilder
from maggma.stores import JSONStore, MemoryStore


@pytest.fixture(scope="session")
def ie_store(test_dir):
    return JSONStore(
        test_dir / "mobility/builder_migration_graph_set.json", key="battery_id"
    )


@pytest.fixture()
def mg_store():
    return MemoryStore()


def test_migration_graph_builder(ie_store, mg_store):
    builder = MigrationGraphBuilder(
        insertion_electrode=ie_store, migration_graph=mg_store
    )
    builder.run()
    assert mg_store.count() == 2
    assert mg_store.count({"state": "successful"}) == 2
    assert mg_store.count({"deprecated": False}) == 2
    d = builder.as_dict()
    assert type(d) is dict
