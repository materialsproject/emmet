from pathlib import Path

import pytest
from maggma.stores import JSONStore, MemoryStore, MongoStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.materials.elasticity import ElasticityBuilder
from emmet.builders.vasp.materials import MaterialsBuilder
from emmet.builders.vasp.task_validator import TaskValidator

#
# @pytest.fixture(scope="session")
# def tasks_store(test_dir):
#     return JSONStore(test_dir / "test_si_tasks.json.gz")
#
#
# @pytest.fixture(scope="session")
# def validation_store(tasks_store):
#     validation_store = MemoryStore()
#     builder = TaskValidator(tasks=tasks_store, task_validation=validation_store)
#     builder.run()
#     return validation_store
#
#
# @pytest.fixture
# def materials_store():
#     return MemoryStore()
#
#
# def test_materials_builder(tasks_store, validation_store, materials_store):
#
#     builder = MaterialsBuilder(
#         tasks=tasks_store, task_validation=validation_store, materials=materials_store
#     )
#     builder.run()
#     assert materials_store.count() == 1
#     assert materials_store.count({"deprecated": False}) == 1
#
#
# def test_serialization(tmpdir):
#     builder = MaterialsBuilder(MemoryStore(), MemoryStore(), MemoryStore())
#
#     dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
#     loadfn(Path(tmpdir) / "test.json")


def get_tasks_store():

    db_info = loadfn(
        "/Users/mjwen/Applications/research_scripts/high_throughput/mp_config/mac/db.json"
    )
    tasks_store = MongoStore(
        database=db_info["database"],
        collection_name=db_info["collection"],
        host=db_info["host"],
        port=db_info["port"],
        username=db_info["admin_user"],
        password=db_info["admin_password"],
    )

    return tasks_store


def get_materials_store():
    return MongoStore(database="elasticity_20220504", collection_name="materials")


def get_elasticity_store():
    return MongoStore(database="elasticity_20220504", collection_name="elasticity")


def get_datetime_query():
    from datetime import datetime

    dt1 = datetime(year=2021, month=8, day=9)
    dt2 = datetime(year=2021, month=8, day=15)
    query = {"last_updated": {"$gte": dt1, "$lte": dt2}}
    # query = {
    #     "last_updated": {"$gte": dt1, "$lte": dt2},
    #     "task_label": {"$regex": "structure opti"},
    # }

    return query


def build_materials():
    tasks_store = get_tasks_store()
    materials_store = get_materials_store()
    builder = MaterialsBuilder(
        tasks=tasks_store, materials=materials_store, query=get_datetime_query()
    )
    builder.run()


def build_elasticity():
    tasks_store = get_tasks_store()
    materials_store = get_materials_store()
    elasticity_store = get_elasticity_store()
    builder = ElasticityBuilder(
        tasks=tasks_store,
        materials=materials_store,
        elasticity=elasticity_store,
        query=get_datetime_query(),
    )
    builder.run()


if __name__ == "__main__":
    build_materials()
    build_elasticity()
