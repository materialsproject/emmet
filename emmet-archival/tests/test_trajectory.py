"""Test trajectory functionality."""

import h5py
import numpy as np
from pathlib import Path
import pytest

from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.core import Structure
from emmet.archival.trajectory import TrajArchive, TrajectoryProperty


def test_traj_prop():
    assert all(
        isinstance(k, str) and isinstance(k, TrajectoryProperty)
        for k in TrajectoryProperty
    )


def test_traj_archive(tmp_dir, sample_task):
    traj_archive = TrajArchive.from_task_doc(sample_task)
    assert isinstance(traj_archive, TrajArchive)
    assert all(
        traj_archive.parsed_objects[TrajectoryProperty[k]] is not None
        for k in (
            "structure",
            "energy",
            "forces",
            "stress",
        )
    )

    assert all(
        isinstance(frame, Structure)
        for frame in traj_archive.parsed_objects["structure"]
    )

    archive_path = Path("traj.h5")
    traj_archive.to_archive("traj.h5")
    assert archive_path.exists()
    with h5py.File(archive_path, "r") as f:
        assert all(
            f.attrs.get(k) is not None
            for k in (
                "constant_lattice",
                "species",
                "num_sites",
                "num_steps",
                "columns",
            )
        )
        assert f["trajectory"].shape == (
            traj_archive.num_steps,
            6 * traj_archive.num_sites
            + 10,  # 3 * num_sites for both coords and forces, 1 for energy, 9 for stress
        )

    pmg_traj = traj_archive.to_pymatgen_trajectory(archive_path)
    assert all(
        frame.get(k) is not None
        for k in (
            "energy",
            "forces",
            "stress",
        )
        for frame in pmg_traj.frame_properties
    )

    # round trip, should be the virtually the same archive
    traj_archive_copy = TrajArchive.from_pymatgen_trajectory(pmg_traj)
    matcher = StructureMatcher()
    assert all(
        matcher.fit(traj_archive_copy.structure[idx], struct)
        for idx, struct in enumerate(traj_archive.structure)
    )

    assert all(
        traj_archive_copy.energy[idx] == pytest.approx(energy)
        for idx, energy in enumerate(traj_archive.energy)
    )

    for k in ("forces", "stress"):
        assert all(
            np.all(
                np.abs(traj_archive_copy.parsed_objects[k][idx] - np.array(obj_arr))
                < 1.0e-6
            )
            for idx, obj_arr in enumerate(traj_archive.parsed_objects[k])
        )
