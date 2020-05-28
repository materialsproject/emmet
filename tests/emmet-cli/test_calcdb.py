import pytest
from datetime import datetime
from maggma.stores import MemoryStore

from emmet.cli.calcdb import CalcDB


@pytest.fixture
def db():
    data = MemoryStore()
    documents = MemoryStore()

    return CalcDB(
        data=data,
        documents=documents,
        doc_keys={"blob": "calcs_reversed.1.blob"},
        removed_keys=["calcs_reversed.0.blob"],
    )


def test_extract_data(db):

    dummy_data1 = {
        "dir_name": "dir1",
        "calcs_reversed": [
            {"blob": "Data to remove", "name": "blob1"},
            {"blob": "Data to extract", "name": "blob2"},
        ],
        "task_id": 1,
        "last_updated": datetime.utcnow(),
    }

    processed = db.extract_data([dummy_data1])

    assert ["blob" not in calc for calc in dummy_data1]
    assert len(processed) == 1
    assert processed[0]["type"] == "blob"
    assert processed[0]["data"] == "Data to extract"
    assert processed[0]["task_id"] == 1
    assert "last_updated" in processed[0]


def test_insert(db):

    dummy_data1 = {
        "dir_name": "dir1",
        "calcs_reversed": [
            {"blob": "Data to remove 1", "name": "blob1"},
            {"blob": "Data to extract 1", "name": "blob2"},
        ],
    }

    processed = db.insert([dummy_data1])
    assert processed[0]["task_id"] == "mp-1"

    dummy_data2 = {
        "dir_name": "dir2",
        "calcs_reversed": [
            {"blob": "Data to remove 2", "name": "blob1"},
            {"blob": "Data to extract 2", "name": "blob2"},
        ],
    }

    processed = db.insert([dummy_data2])

    assert processed[0]["task_id"] == "mp-2"


def test_insert_duplicates(db):

    dummy_data2 = {
        "dir_name": "dir2",
        "calcs_reversed": [
            {"blob": "Data to remove 2", "name": "blob1"},
            {"blob": "Data to extract 2", "name": "blob2"},
        ],
    }

    processed = db.insert([dummy_data2])

    assert processed[0]["task_id"] == "mp-1"

    assert len(db.insert([dummy_data2])) == 0
    assert len(db.insert([dummy_data2], update_duplicates=True)) == 1


def test_insert_force_task_id(db):

    dummy_data3 = {
        "dir_name": "dir2",
        "task_id": "mp-343",
        "calcs_reversed": [
            {"blob": "Data to remove 2", "name": "blob1"},
            {"blob": "Data to extract 2", "name": "blob2"},
        ],
    }

    processed = db.insert([dummy_data3])
    assert len(processed) == 1
    assert processed[0]["task_id"] == "mp-343"
