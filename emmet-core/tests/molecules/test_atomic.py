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
        d["last_updated"] = datetime.datetime.strptime(
            d["last_updated"]["string"], "%Y-%m-%d %H:%M:%S.%f"
        )

    tasks = [TaskDocument(**t) for t in data]
    return tasks


@pytest.fixture(scope="session")
def open_shell(test_dir):
    task = TaskDocument(**loadfn((test_dir / "open_shell_nbo_task.json.gz")))
    return task


def test_partial_charges(test_tasks):
    # Test RESP
    pcd = PartialChargesDoc.from_task(
        test_tasks[0],
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["resp"],
    )

    assert pcd.property_name == "partial_charges"
    assert pcd.method == "resp"
    assert pcd.partial_charges == test_tasks[0].output.resp

    # Test Mulliken
    pcd = PartialChargesDoc.from_task(
        test_tasks[0],
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["mulliken"],
    )

    assert pcd.method == "mulliken"
    assert pcd.partial_charges == test_tasks[0].output.mulliken

    # Test Critic2
    pcd = PartialChargesDoc.from_task(
        test_tasks[3],
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["critic2"],
    )

    assert pcd.method == "critic2"
    assert pcd.partial_charges == test_tasks[3].critic2["processed"]["charges"]

    # Test NBO
    pcd = PartialChargesDoc.from_task(
        test_tasks[4],
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["nbo"],
    )

    assert pcd.method == "nbo"
    nbo_charges = [
        float(test_tasks[4].output.nbo["natural_populations"][0]["Charge"][str(i)])
        for i in range(11)
    ]
    assert pcd.partial_charges == nbo_charges


def test_partial_spins(open_shell):
    # Test Mulliken
    psd = PartialSpinsDoc.from_task(
        open_shell,
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["mulliken"],
    )

    assert psd.property_name == "partial_spins"
    assert psd.method == "mulliken"
    assert psd.partial_spins == [m[1] for m in open_shell.output.mulliken]

    # Test NBO
    psd = PartialSpinsDoc.from_task(
        open_shell,
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["nbo"],
    )

    assert psd.method == "nbo"
    spins = [
        float(open_shell.output.nbo["natural_populations"][0]["Density"][str(i)])
        for i in range(11)
    ]
    assert psd.partial_spins == spins
