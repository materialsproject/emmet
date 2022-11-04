import json
import datetime
import copy

import pytest

from monty.io import zopen
from monty.serialization import loadfn

from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.thermo import ThermoDoc, get_free_energy


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
def sp(test_dir):
    data = loadfn((test_dir / "closed_shell_nbo_task.json.gz").as_posix())
    task = TaskDocument(**data)

    return task

@pytest.mark.skip(reason="Waiting on molecule update.")
def test_thermo(test_tasks, sp):
    # Just energy; no free energy information
    doc = ThermoDoc.from_task(task=sp, molecule_id="test-123456", deprecated=False)

    assert doc.property_name == "thermo"
    assert doc.electronic_energy == sp.output.final_energy * 27.2114
    assert doc.free_energy is None

    # With all thermodynamic information
    task = test_tasks[0]
    doc = ThermoDoc.from_task(task, molecule_id="test-123456", deprecated=False)

    assert doc.electronic_energy == task.output.final_energy * 27.2114
    assert doc.total_enthalpy == task.output.enthalpy * 0.043363
    assert doc.total_entropy == task.output.entropy * 0.000043363
    assert doc.free_energy == get_free_energy(
        task.output.final_energy, task.output.enthalpy, task.output.entropy
    )
    assert doc.rt == task.calcs_reversed[0]["gas_constant"] * 0.043363
    assert doc.vibrational_enthalpy == task.calcs_reversed[0]["vib_enthalpy"] * 0.043363
