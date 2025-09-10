import numpy as np
from pytest import approx, fixture

from monty.serialization import loadfn
from pymatgen.core import Element, Structure, Molecule
from pymatgen.core.trajectory import Trajectory as PmgTraj

from emmet.core.tasks import TaskDoc
from emmet.core.testing_utils import DataArchive
from emmet.core.trajectory import Trajectory


@fixture(scope="module")
def si_task(test_dir):
    with DataArchive.extract(
        test_dir / "vasp" / "Si_old_double_relax.json.gz"
    ) as dir_name:
        return TaskDoc.from_directory(dir_name)


def test_reorder_sites():
    # Test that site ordering works correctly

    lattice = [[5.0, 0, 0], [4, 0, 0], [4.5, 0, 0]]
    coords = [
        [0, 0, 0],
        [0.0, 0.25, 0.0],
        [0.25, 0.0, 0.25],
        [0.0, 0.0, 0.25],
        [0.25, 0.0, 0.0],
        [0.25, 0.25, 0.25],
        [0.5, 0.5, 0.5],
        [0.75, 0.75, 0.75],
    ]

    elements = ["Si", "Si", "Ti", "N", "Ga", "As", "N", "Cu"]
    ref_z = [Element(ele).Z for ele in elements]

    # try a number of times to ensure ordering is always OK
    for _ in range(2 * len(elements)):
        new_z = [z for z in ref_z]
        np.random.shuffle(new_z)

        structure = Structure(lattice, [Element.from_Z(z) for z in new_z], coords)
        reordered_struct, reordered_idx = Trajectory.reorder_sites(structure, ref_z)
        assert all(site.specie.Z == ref_z[i] for i, site in enumerate(reordered_struct))
        assert all(
            np.abs(np.linalg.norm(reordered_struct[i].coords - structure[old_i].coords))
            < 1e-6
            for i, old_i in enumerate(reordered_idx)
        )

        # ensur that these also work for Molecules
        mol = Molecule.from_sites(structure)
        reordered_mol, reordered_idx = Trajectory.reorder_sites(structure, ref_z)
        assert all(site.specie.Z == ref_z[i] for i, site in enumerate(reordered_mol))
        assert all(
            np.abs(np.linalg.norm(reordered_mol[i].coords - mol[old_i].coords)) < 1e-6
            for i, old_i in enumerate(reordered_idx)
        )


def test_task_doc(si_task):
    traj = Trajectory.from_task_doc(si_task)[0]
    assert traj.num_ionic_steps == sum(
        len(cr.output.ionic_steps) for cr in si_task.calcs_reversed
    )
    istep = -1
    for cr in si_task.calcs_reversed:
        for ionic_step in cr.output.ionic_steps:
            assert traj.energy[istep] == approx(ionic_step.e_0_energy)
            istep -= 1


def test_parquet(si_task, tmp_dir):
    parqet_file = "test.parquet"

    traj = Trajectory.from_task_doc(si_task)[0]
    traj.to(parqet_file, compression="GZIP")

    new_traj = Trajectory.from_parquet(parqet_file)
    assert hash(new_traj) == hash(traj)


def test_pmg(si_task):
    traj = Trajectory.from_task_doc(si_task)[0]
    pmg_traj = traj.to(fmt="PMG")
    assert isinstance(pmg_traj, PmgTraj)
    assert len(pmg_traj) == traj.num_ionic_steps
    assert len(pmg_traj.frame_properties) == traj.num_ionic_steps

    # some float-rounding that happens here on round trip
    roundtrip = Trajectory.from_pmg(pmg_traj)

    for k in Trajectory.model_fields:
        if k == "ionic_step_properties":
            continue

        if (
            k
            in (
                "num_ionic_steps",
                "electronic_steps",
                "task_type",
                "run_type",
            )
            or getattr(traj, k, None) is None
        ):
            # Can't easily test for equality of electronic steps without bespoke code
            continue

        assert all(
            np.all(np.abs(np.array(new_val) - np.array(getattr(traj, k)[i])) < 1e-6)
            for i, new_val in enumerate(getattr(roundtrip, k))
        )


def test_mixed_calc_type(test_dir):
    # Test that Trajectory correctly creates new Trajectories for every
    # sequential calculation of different CalcType

    three_cr_task_dict = loadfn(test_dir / "mp-1120260_cr.json.gz")
    trajs = Trajectory.from_task_doc(TaskDoc(**three_cr_task_dict))
    assert len(trajs) == 2  # GGA static followed by two SCAN relaxes
    assert trajs[0].task_type.value == "Static"
    assert trajs[0].run_type.value == "GGA"

    assert trajs[1].task_type.value == "Structure Optimization"
    assert trajs[1].run_type.value == "SCAN"

    # now exchange order of calcs_reversed to get three trajectories
    three_cr_task_dict["calcs_reversed"] = [
        three_cr_task_dict["calcs_reversed"][idx] for idx in (0, 2, 1)
    ]
    trajs = Trajectory.from_task_doc(TaskDoc(**three_cr_task_dict))
    assert len(trajs) == 3  # SCAN relax -> GGA static -> SCAN relax
    assert trajs[1].task_type.value == "Static"
    assert trajs[1].run_type.value == "GGA"

    for idx in (
        0,
        2,
    ):
        assert trajs[idx].task_type.value == "Structure Optimization"
        assert trajs[idx].run_type.value == "SCAN"
