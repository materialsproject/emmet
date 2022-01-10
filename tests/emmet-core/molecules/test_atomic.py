import json
import datetime

import pytest

from monty.io import zopen
from monty.serialization import loadfn

from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.atomic import PartialChargesDoc, PartialSpinsDoc


@pytest.fixture(scope="session")
def test_tasks(test_dir):
    with zopen(test_dir / "liec_tasks.json.gz") as f:
        data = json.load(f)

    for d in data:
        d["last_updated"] = datetime.datetime.strptime(d["last_updated"]["string"], "%Y-%m-%d %H:%M:%S.%f")

    tasks = [TaskDocument(**t) for t in data]
    return tasks


def test_partial_charges(test_tasks):
    # Test RESP
    pcd = PartialChargesDoc.from_task(test_tasks[0], molecule_id="libe-115880", preferred_methods=("RESP",))

    assert pcd.property_name == "partial_charges"
    assert pcd.method == "RESP"
    assert pcd.charges == test_tasks[0].output.resp

    # Test Mulliken
    pcd = PartialChargesDoc.from_task(test_tasks[0], molecule_id="libe-115880", preferred_methods=("Mulliken",))

    assert pcd.method == "Mulliken"
    assert pcd.charges == test_tasks[0].output.mulliken

    # Test Critic2
    pcd = PartialChargesDoc.from_task(test_tasks[3], molecule_id="libe-115880", preferred_methods=("Critic2",))

    assert pcd.method == "Critic2"
    assert pcd.charges == test_tasks[3].critic2["processed"]["charges"]

    # Test NBO
    pcd = PartialChargesDoc.from_task(test_tasks[4], molecule_id="libe-115880", preferred_methods=("NBO7",))

    assert pcd.method == "NBO7"
    nbo_charges = [float(test_tasks[4].output.nbo["natural_populations"][0]["Charge"][str(i)]) for i in range(11)]
    assert pcd.charges == nbo_charges