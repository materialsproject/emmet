import pytest

from monty.serialization import loadfn

from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.thermo import MoleculeThermoDoc, get_free_energy


@pytest.fixture(scope="session")
def sp(test_dir):
    data = loadfn((test_dir / "closed_shell_nbo_task.json.gz").as_posix())
    task = TaskDocument(**data)

    return task


def test_thermo(liec_tasks, sp):
    # Just energy; no free energy information
    doc = MoleculeThermoDoc.from_task(
        task=sp,
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        deprecated=False,
    )

    assert doc.property_name == "thermo"
    assert doc.electronic_energy == sp.output.final_energy * 27.2114
    assert doc.free_energy is None

    # With all thermodynamic information
    task = liec_tasks[0]
    doc = MoleculeThermoDoc.from_task(
        task,
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        deprecated=False,
    )

    assert doc.electronic_energy == task.output.final_energy * 27.2114
    assert doc.total_enthalpy == task.output.enthalpy * 0.043363
    assert doc.total_entropy == task.output.entropy * 0.000043363
    assert doc.free_energy == get_free_energy(
        task.output.final_energy, task.output.enthalpy, task.output.entropy
    )
    assert doc.rt == task.calcs_reversed[0]["gas_constant"] * 0.043363
    assert doc.vibrational_enthalpy == task.calcs_reversed[0]["vib_enthalpy"] * 0.043363
