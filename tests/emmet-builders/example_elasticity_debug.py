from pathlib import Path

import pytest
from maggma.stores import JSONStore, MemoryStore, MongoStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.materials.elasticity import ElasticityBuilder
from emmet.builders.vasp.materials import MaterialsBuilder
from emmet.builders.vasp.task_validator import TaskValidator


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


# def get_materials_store():
#
#     db_info = loadfn(
#         "/Users/mjwen/Applications/research_scripts/high_throughput/mp_config/mac/db.json"
#     )
#     return MongoStore(
#         database=db_info["database"],
#         collection_name="materials_build_20220511",
#         host=db_info["host"],
#         port=db_info["port"],
#         username=db_info["admin_user"],
#         password=db_info["admin_password"],
#     )


def get_materials_store():
    return MongoStore(database="elasticity_20220527", collection_name="materials")


def get_elasticity_store():
    return MongoStore(database="elasticity_20220527", collection_name="elasticity")


def get_datetime_query():
    from datetime import datetime

    dt1 = datetime(year=2021, month=8, day=9)
    dt2 = datetime(year=2021, month=8, day=15)
    query = {"last_updated": {"$gte": dt1, "$lte": dt2}}
    # query = {
    #     "last_updated": {"$gte": dt1, "$lte": dt2},
    #     "task_label": {"$regex": "structure opti"},
    # }
    query = {"formula_pretty": "Nb3Cr"}

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
        # query=get_datetime_query(),
    )
    builder.run()


if __name__ == "__main__":
    build_materials()
    build_elasticity()
