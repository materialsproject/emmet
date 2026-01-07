import json
import copy
import datetime

import pytest

import numpy as np

from monty.io import zopen

from pymatgen.core.structure import Molecule

from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.trajectory import ForcesDoc, TrajectoryDoc


@pytest.fixture(scope="session")
def force_calc(test_dir):
    with zopen(test_dir / "force_trajectory" / "force_calc.json.gz", "rt") as f:
        data = json.load(f)

    data["last_updated"] = datetime.datetime.now()

    task = TaskDocument(**data)
    return task


@pytest.fixture(scope="session")
def ffopt_task(test_dir):
    with zopen(test_dir / "force_trajectory" / "ffopt_calc.json.gz", "rt") as f:
        data = json.load(f)

    data["last_updated"] = datetime.datetime.now()

    task = TaskDocument(**data)
    return task


def test_forces(force_calc):
    doc = ForcesDoc.from_task(
        force_calc, molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )
    assert doc.property_name == "forces"
    assert len(doc.forces) == 11
    assert np.allclose(np.array(doc.forces), np.array(doc.precise_forces), atol=0.001)
    assert doc.cds_forces is None
    assert doc.average_force_magnitude == pytest.approx(0.03861184536372114)
    assert doc.max_force_magnitude == pytest.approx(0.07195037119572352)
    assert doc.min_force_magnitude == pytest.approx(0.003093974384847178)


def test_trajectory(ffopt_task):
    doc = TrajectoryDoc.from_task(
        ffopt_task, molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )

    assert doc.property_name == "optimization_trajectory"
    assert doc.num_trajectories == 2
    assert len(doc.geometries) == doc.num_trajectories
    assert len(doc.energies) == doc.num_trajectories
    assert len(doc.forces) == doc.num_trajectories

    assert doc.species == ["C", "C", "C", "O", "C", "N", "O", "N", "N", "H", "H", "H"]
    assert len(doc.geometries[0]) == 13
    assert doc.energies[0][0] == pytest.approx(-468.1895254889)

    mol_objects = doc.molecules
    assert isinstance(mol_objects[0][0], Molecule)
    assert len(mol_objects) == doc.num_trajectories

    traj_objects = doc.as_trajectories()
    assert len(traj_objects) == 2


def test_missing_trajectory(ffopt_task):
    # Mess with one of the trajectories, removing gradients
    missing_grad = copy.deepcopy(ffopt_task)

    missing_grad.calcs_reversed[-1]["gradients"] = list()

    doc = TrajectoryDoc.from_task(
        missing_grad, molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )

    # The trajectory with missing gradients should not be included
    assert doc.num_trajectories == 1

    # Likewise, if there are missing geometries
    missing_geom = copy.deepcopy(ffopt_task)

    missing_geom.calcs_reversed[-1]["geometries"] = list()

    doc = TrajectoryDoc.from_task(
        missing_geom, molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )
    assert doc.num_trajectories == 1

    # And missing energies
    missing_energies = copy.deepcopy(ffopt_task)
    missing_energies.calcs_reversed[-1]["energy_trajectory"] = None

    doc = TrajectoryDoc.from_task(
        missing_energies, molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )
    assert doc.num_trajectories == 1
