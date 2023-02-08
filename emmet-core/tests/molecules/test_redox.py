import pytest

from monty.serialization import loadfn

from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.thermo import ThermoDoc
from emmet.core.molecules.redox import RedoxDoc


@pytest.fixture(scope="session")
def base_mol(test_dir):
    mol = loadfn((test_dir / "redox_doc" / "base_mol.json").as_posix())
    mol_doc = MoleculeDoc(**mol)
    return mol_doc


@pytest.fixture(scope="session")
def base_thermo(test_dir):
    thermo = loadfn((test_dir / "redox_doc" / "thermo.json").as_posix())
    thermo_doc = ThermoDoc(**thermo)
    return thermo_doc


@pytest.fixture(scope="session")
def red_thermo(test_dir):
    thermo = loadfn((test_dir / "redox_doc" / "red_thermo.json").as_posix())
    thermo_doc = ThermoDoc(**thermo)
    return thermo_doc

@pytest.fixture(scope="session")
def ox_thermo(test_dir):
    thermo = loadfn((test_dir / "redox_doc" / "ox_thermo.json").as_posix())
    thermo_doc = ThermoDoc(**thermo)
    return thermo_doc


@pytest.fixture(scope="session")
def ie_task(test_dir):
    task = loadfn((test_dir / "redox_doc" / "ie_task.json").as_posix())
    task_doc = TaskDocument(**task)
    return task_doc


@pytest.fixture(scope="session")
def ea_task(test_dir):
    task = loadfn((test_dir / "redox_doc" / "ea_task.json").as_posix())
    task_doc = TaskDocument(**task)
    return task_doc


def test_redox(base_mol, base_thermo, red_thermo, ox_thermo, ie_task, ea_task):
    redox_doc = RedoxDoc.from_docs(base_molecule_doc=base_mol,
                                   base_thermo_doc=base_thermo,
                                   red_doc=red_thermo,
                                   ox_doc=ox_thermo,
                                   ea_doc=ea_task,
                                   ie_doc=ie_task)

    assert redox_doc.electron_affinity == pytest.approx(-3.3024638499209686)
    assert redox_doc.ionization_energy == pytest.approx(4.903294672107222)
    assert redox_doc.oxidation_free_energy == pytest.approx(3.9880055108133092)
    assert redox_doc.reduction_free_energy == pytest.approx(-4.237271030198826)