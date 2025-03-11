import numpy as np
from pathlib import Path
from pytest import approx

from pymatgen.core.trajectory import Trajectory as PmgTraj
from pymatgen.util.testing import PymatgenTest

from emmet.core.tasks import TaskDoc
from emmet.core.trajectory import Trajectory


class TestTrajectory(PymatgenTest):
    def setUp(self):
        self.test_dir = (
            Path(__file__).parent.parent.parent.joinpath("test_files").resolve()
        )
        self.task_doc = TaskDoc.from_directory(
            self.test_dir / "vasp" / "Si_old_double_relax"
        )

    def test_task_doc(self):
        traj = Trajectory.from_task_doc(self.task_doc)
        assert traj.num_ionic_steps == sum(
            len(cr.output.ionic_steps) for cr in self.task_doc.calcs_reversed
        )
        istep = -1
        for cr in self.task_doc.calcs_reversed:
            for ionic_step in cr.output.ionic_steps:
                assert traj.energy[istep] == approx(ionic_step.e_0_energy)
                istep -= 1

    def test_parquet(self):
        parqet_file = "test.parquet.gz"

        traj = Trajectory.from_task_doc(self.task_doc)
        traj.to(parqet_file)

        new_traj = Trajectory.from_parquet(parqet_file)
        assert hash(new_traj) == hash(traj)

    def test_pmg(self):
        traj = Trajectory.from_task_doc(self.task_doc)
        pmg_traj = traj.to(fmt="PMG")
        assert isinstance(pmg_traj, PmgTraj)
        assert len(pmg_traj) == traj.num_ionic_steps
        assert len(pmg_traj.frame_properties) == traj.num_ionic_steps

        # some float-rounding that happens here on round trip
        roundtrip = Trajectory.from_pmg(pmg_traj)

        for k in Trajectory.model_fields:
            if (
                k
                in (
                    "num_ionic_steps",
                    "electronic_steps",
                )
                or getattr(traj, k, None) is None
            ):
                # Can't easily test for equality of electronic steps without bespoke code
                continue

            assert all(
                np.all(np.abs(np.array(new_val) - np.array(getattr(traj, k)[i])) < 1e-6)
                for i, new_val in enumerate(getattr(roundtrip, k))
            )
