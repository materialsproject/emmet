"""Test the row of the trajectory table: what it holds, and that it rebuilds."""

from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from emmet.core import ARROW_COMPATIBLE
from emmet.core.io.pymatgen import Structure, Vasprun
from emmet.core.tasks import TaskDoc, _get_max_force
from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.vasp.calculation import Calculation, get_trajectories_from_calculations
from emmet.core.vasp.outcar import StepMagnetization, read_step_magnetization
from emmet.core.vasp.parse import DirectorySource, ParsePolicy, parse_calculation
from emmet.core.vasp.parsed import PARSED_TABLES, SpinMode, TrajectoryRow

if ARROW_COMPATIBLE:
    import io

    import pyarrow as pa
    import pyarrow.parquet as pq

    from emmet.core.arrow import arrowize

HEADER = {
    "identifier": "mp-1",
    "completed_at": datetime(2020, 3, 11, 1, 50, 16, tzinfo=UTC),
    "run_type": RunType.GGA,
    "task_type": TaskType.Structure_Optimization,
    "formula_pretty": "Si",
    "chemsys": "Si",
}


def parse(fixture, suffix=None):
    """The parsed calculation, its vasprun and its directory contents (until it is removed)."""
    with DataArchive.extract(TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz") as d:
        sources = DirectorySource.from_directory(d)
        source = next(s for s in sources if suffix in (None, s.calc_suffix))
        parsed = parse_calculation(source, "aaaaaaab", ParsePolicy())
        rows = list(parsed.objects())
        name = f"vasprun.xml{'' if suffix is None else '.' + suffix}.gz"
        vasprun = Vasprun(
            d / name, parse_potcar_file=False, parse_dos=False, parse_eigen=False
        )
    return parsed, vasprun, rows


@pytest.fixture(scope="module")
def relax():
    """A collinear relaxation of 3 sites, 6 ionic steps."""
    return parse("r2scan_relax")


@pytest.fixture(scope="module")
def fixed_cell():
    """ISIF = 0: no stress is calculated."""
    return parse("defect_run")


@pytest.fixture(scope="module")
def unpolarized():
    return parse("r2scan_scf_line")


class TestValues:
    def test_a_row_is_made(self, relax):
        parsed, vasprun, _ = relax
        row = parsed.trajectory
        assert isinstance(row, TrajectoryRow)
        assert parsed.errors == []
        assert (row.identifier, row.num_ionic_steps) == ("aaaaaaab", 6)
        assert row.species == [site.specie.symbol for site in vasprun.final_structure]
        # the header is that of the task
        assert row.run_type == parsed.task.run_type
        assert row.task_type == parsed.task.task_type
        assert row.completed_at == parsed.completed_at
        assert row.formula_pretty == parsed.task.formula_pretty
        assert (row.year, row.month, row.day) == (
            parsed.completed_at.year,
            parsed.completed_at.month,
            parsed.completed_at.day,
        )

    def test_the_arrays_are_those_of_the_vasprun(self, relax):
        parsed, vasprun, _ = relax
        row = parsed.trajectory
        steps = vasprun.ionic_steps
        n, sites = len(steps), len(row.species)

        np.testing.assert_allclose(
            np.reshape(row.lattice, (n, 3, 3)),
            [s["structure"].lattice.matrix for s in steps],
        )
        np.testing.assert_allclose(
            np.reshape(row.frac_coords, (n, sites, 3)),
            [s["structure"].frac_coords for s in steps],
        )
        np.testing.assert_allclose(
            np.reshape(row.forces, (n, sites, 3)), [s["forces"] for s in steps]
        )
        np.testing.assert_allclose(
            np.reshape(row.stress, (n, 3, 3)), [s["stress"] for s in steps]
        )
        for column, key in (
            ("energy", "e_0_energy"),
            ("free_energy", "e_fr_energy"),
            ("energy_wo_entropy", "e_wo_entrp"),
        ):
            assert getattr(row, column) == [s[key] for s in steps]

    def test_the_scf_steps(self, relax):
        parsed, vasprun, _ = relax
        row = parsed.trajectory
        scf = [e for s in vasprun.ionic_steps for e in s["electronic_steps"]]
        assert row.num_scf_steps == [
            len(s["electronic_steps"]) for s in vasprun.ionic_steps
        ]
        assert sum(row.num_scf_steps) == len(scf) == 268
        for column, key in (
            ("scf_energy", "e_0_energy"),
            ("scf_free_energy", "e_fr_energy"),
            ("scf_energy_wo_entropy", "e_wo_entrp"),
        ):
            assert getattr(row, column) == [e[key] for e in scf]
        # the last SCF step of an ionic step is the energy of the ionic step
        ends = np.cumsum(row.num_scf_steps) - 1
        assert np.array(row.scf_energy)[ends].tolist() == row.energy
        assert np.array(row.scf_free_energy)[ends].tolist() == row.free_energy

    def test_the_settings(self, relax):
        row = relax[0].trajectory
        parameters = relax[1].parameters
        assert (row.ediff, row.ediffg, row.nelm, row.nsw, row.ibrion, row.isif) == (
            parameters["EDIFF"],
            parameters["EDIFFG"],
            parameters["NELM"],
            parameters["NSW"],
            parameters["IBRION"],
            parameters["ISIF"],
        )
        assert row.potim == parameters["POTIM"]

    def test_partitioned_by_run_type(self):
        spec = PARSED_TABLES["trajectories"]
        assert spec.row_model is TrajectoryRow and spec.partition_by == ("run_type",)
        assert spec.ordered_columns[:3] == ["identifier", "completed_at", "year"]


class TestMaxForce:
    def test_it_is_the_largest_force_on_an_atom(self, relax):
        parsed, vasprun, _ = relax
        forces = np.array([s["forces"] for s in vasprun.ionic_steps])
        np.testing.assert_allclose(
            parsed.trajectory.max_force, np.linalg.norm(forces, axis=2).max(axis=1)
        )

    def test_it_agrees_with_the_force_the_task_uses(self, relax, monkeypatch):
        """The last value is what `AnalysisDoc.max_force` is."""
        parsed, vasprun, _ = relax
        calc = SimpleNamespace(
            output=SimpleNamespace(
                ionic_steps=[
                    SimpleNamespace(forces=vasprun.ionic_steps[-1]["forces"].tolist())
                ],
                structure=vasprun.final_structure,
            )
        )
        assert parsed.trajectory.max_force[-1] == pytest.approx(_get_max_force(calc))

    def test_fixed_components_do_not_count(self):
        """Selective dynamics: VASP does not test the components it does not move."""
        structure = Structure(np.eye(3) * 4, ["Si", "Si"], [[0, 0, 0], [0.5, 0.5, 0.5]])
        step = SimpleNamespace(
            structure=structure,
            forces=[[0.0, 0.0, 5.0], [0.3, 0.4, 0.0]],
            stress=None,
            e_0_energy=-1.0,
            e_fr_energy=-1.0,
            e_wo_entrp=-1.0,
            electronic_steps=[],
        )
        free = [[True, True, False], [True, True, True]]
        row = TrajectoryRow.from_ionic_steps([step], selective_dynamics=free, **HEADER)
        assert row.max_force == [pytest.approx(0.5)]
        assert row.selective_dynamics == free
        without = TrajectoryRow.from_ionic_steps([step], **HEADER)
        assert without.max_force == [pytest.approx(5.0)]
        assert without.selective_dynamics is None


class TestIncompleteSteps:
    """A quantity is stored if every ionic step has it."""

    def steps(self, vasprun, **missing):
        return [
            SimpleNamespace(
                structure=s["structure"],
                forces=None if i in missing.get("forces", ()) else s["forces"],
                stress=s["stress"],
                e_0_energy=s["e_0_energy"],
                e_fr_energy=s["e_fr_energy"],
                e_wo_entrp=s["e_wo_entrp"],
                electronic_steps=[
                    SimpleNamespace(
                        e_0_energy=e["e_0_energy"],
                        e_fr_energy=(
                            None if i in missing.get("scf", ()) else e["e_fr_energy"]
                        ),
                        e_wo_entrp=e["e_wo_entrp"],
                    )
                    for e in s["electronic_steps"]
                ],
            )
            for i, s in enumerate(vasprun.ionic_steps)
        ]

    def test_a_step_without_forces_leaves_the_forces_out(self, relax):
        row = TrajectoryRow.from_ionic_steps(self.steps(relax[1], forces={2}), **HEADER)
        assert row.forces is None and row.max_force is None
        assert row.stress is not None and row.energy is not None

    def test_a_scf_step_without_an_energy_leaves_that_energy_out(self, relax):
        row = TrajectoryRow.from_ionic_steps(self.steps(relax[1], scf={1}), **HEADER)
        assert row.scf_free_energy is None
        assert row.scf_energy is not None and row.scf_energy_wo_entropy is not None
        assert row.num_scf_steps == relax[0].trajectory.num_scf_steps

    def test_magnetization_for_other_steps_is_ignored(self, relax):
        magnetization = StepMagnetization(
            magmoms=[np.zeros(3)] * 5, total=[np.zeros(1)] * 5
        )
        row = TrajectoryRow.from_ionic_steps(
            self.steps(relax[1]), magnetization=magnetization, **HEADER
        )
        assert row.magmoms is None and row.total_magnetization is None

    def test_a_step_without_moments_leaves_all_of_them_out(self, relax):
        magnetization = StepMagnetization(
            magmoms=[np.zeros(3)] * 5 + [None], total=[np.zeros(1)] * 6
        )
        row = TrajectoryRow.from_ionic_steps(
            self.steps(relax[1]),
            parameters={"ISPIN": 2},
            magnetization=magnetization,
            **HEADER,
        )
        assert row.magmoms is None and row.total_magnetization is not None


class TestFixedCell:
    """ISIF = 0 calculations have no stress, so the stress column is null."""

    def test_the_calculation_is_parsed(self, fixed_cell):
        parsed, vasprun, rows = fixed_cell
        assert vasprun.parameters["ISIF"] == 0
        assert parsed.errors == [] and parsed.outcome.value == "parsed"
        assert parsed.task is not None and parsed.trajectory is not None

    def test_the_trajectory_models_leave_out_the_stress_too(self):
        """RelaxTrajectory, which TaskDoc and CoreTaskDoc.from_directory use, rejected it."""
        from emmet.core.tasks import CoreTaskDoc

        with DataArchive.extract(TEST_FILES_DIR / "vasp" / "defect_run.json.gz") as d:
            doc, trajectory = CoreTaskDoc.from_directory(d)
            full = TaskDoc.from_directory(d)
        assert trajectory.stress is None and trajectory.forces is not None
        assert doc.task_type is not None and full.output.stress is None

    def test_it_has_no_stress(self, fixed_cell):
        row = fixed_cell[0].trajectory
        assert row.stress is None
        assert row.forces is not None and row.max_force is not None
        assert row.isif == 0


class TestMagnetization:
    def test_moments_of_every_step(self, relax):
        parsed, vasprun, _ = relax
        row = parsed.trajectory
        with DataArchive.extract(
            TEST_FILES_DIR / "vasp" / "r2scan_relax.json.gz"
        ) as directory:
            reference = read_step_magnetization(directory / "OUTCAR.gz")
        assert row.spin_mode == SpinMode.COLLINEAR
        moments = np.reshape(row.magmoms, (6, 3))
        np.testing.assert_allclose(moments, np.array(reference.magmoms))
        # the moments change as the relaxation goes
        assert not np.allclose(moments[0], moments[-1])
        np.testing.assert_allclose(
            row.total_magnetization, np.array(reference.total).ravel()
        )

    def test_the_last_step_is_the_final_moments_of_the_task(self, relax):
        parsed, _, _ = relax
        row = parsed.trajectory
        final = np.reshape(row.magmoms, (6, 3))[-1]
        assert final.tolist() == pytest.approx(
            [site["tot"] for site in parsed.task.output.outcar["magnetization"]]
        )
        assert row.total_magnetization[-1] == pytest.approx(
            parsed.task.output.outcar["total_magnetization"]
        )

    def test_none_without_spin(self, unpolarized):
        parsed, _, _ = unpolarized
        row = parsed.trajectory
        assert row.spin_mode == SpinMode.UNPOLARIZED
        assert row.magmoms is None and row.total_magnetization is None
        assert parsed.errors == []

    def test_noncollinear_moments(self, relax):
        parsed, vasprun, _ = relax
        steps = [
            SimpleNamespace(
                structure=s["structure"],
                forces=s["forces"],
                stress=s["stress"],
                e_0_energy=s["e_0_energy"],
                e_fr_energy=s["e_fr_energy"],
                e_wo_entrp=s["e_wo_entrp"],
                electronic_steps=[],
            )
            for s in vasprun.ionic_steps
        ]
        magnetization = StepMagnetization(
            magmoms=[np.arange(9.0).reshape(3, 3) + i for i in range(6)],
            total=[np.array([0.1, 0.2, 0.3])] * 6,
        )
        row = TrajectoryRow.from_ionic_steps(
            steps,
            parameters={"LNONCOLLINEAR": True, "ISPIN": 2},
            magnetization=magnetization,
            **HEADER,
        )
        assert row.spin_mode == SpinMode.NONCOLLINEAR
        assert len(row.magmoms) == 6 * 3 * 3 and len(row.total_magnetization) == 18
        assert np.reshape(row.magmoms, (6, 3, 3))[2, 1].tolist() == [5.0, 6.0, 7.0]
        # the moments are a site property of the structures
        assert row.structures[2][1].properties["magmom"] == [5.0, 6.0, 7.0]

    def test_other_numbers_of_steps_are_an_error_and_leave_them_out(self, monkeypatch):
        import emmet.core.vasp.parse as parse_module

        monkeypatch.setattr(
            parse_module,
            "read_step_magnetization",
            lambda path: StepMagnetization(magmoms=[None], total=[None]),
        )
        parsed, _, rows = parse("r2scan_relax")
        assert any("magnetic moments" in error for error in parsed.errors)
        assert parsed.trajectory is not None
        assert parsed.trajectory.magmoms is None
        assert parsed.trajectory.total_magnetization is None
        assert parsed.outcome.value == "parsed" and parsed.task is not None

    def test_an_unreadable_outcar_is_an_error(self, monkeypatch):
        import emmet.core.vasp.parse as parse_module

        def fail(path):
            raise OSError("cannot read")

        monkeypatch.setattr(parse_module, "read_step_magnetization", fail)
        parsed, _, _ = parse("r2scan_relax")
        assert any("cannot read" in error for error in parsed.errors)
        assert parsed.trajectory is not None and parsed.trajectory.magmoms is None


class TestErrors:
    def test_a_trajectory_which_cannot_be_made_does_not_fail_the_calculation(
        self, monkeypatch
    ):
        def fail(*args, **kwargs):
            raise ValueError("no good")

        monkeypatch.setattr(TrajectoryRow, "from_ionic_steps", classmethod(fail))
        parsed, _, rows = parse("Si_uniform")
        assert parsed.trajectory is None
        assert any("the trajectory" in error for error in parsed.errors)
        assert parsed.outcome.value == "parsed" and parsed.task is not None
        assert rows, "the large objects of the calculation are still parsed"
        assert parsed.manifest_row().errors == parsed.errors

    def test_no_ionic_steps(self):
        with pytest.raises(ValueError, match="no ionic steps"):
            TrajectoryRow.from_ionic_steps([], **HEADER)

    def test_the_sites_must_stay_the_same(self, relax):
        _, vasprun, _ = relax
        steps = [
            SimpleNamespace(structure=s["structure"], electronic_steps=[])
            for s in vasprun.ionic_steps[:2]
        ]
        steps[1].structure = steps[1].structure.copy()
        steps[1].structure.replace(0, "Ge")
        with pytest.raises(ValueError, match="not the same"):
            TrajectoryRow.from_ionic_steps(steps, **HEADER)

    @pytest.mark.parametrize(
        "change, match",
        [
            ({"forces": [0.0] * 5}, "forces"),
            ({"energy": [0.0]}, "ionic steps"),
            ({"scf_energy": [0.0]}, "SCF steps"),
            ({"magmoms": [0.0]}, "magmoms"),
            ({"lattice": [0.0] * 9}, "lattice"),
        ],
    )
    def test_the_shapes_are_checked(self, relax, change, match):
        config = {**relax[0].trajectory.model_dump(), **change}
        with pytest.raises(ValidationError, match=match):
            TrajectoryRow(**config)


class TestConvergence:
    @pytest.mark.parametrize(
        "kind, old_key",
        [
            ("energy", "energy"),
            ("free_energy", "e_fr_energy"),
            ("energy_wo_entropy", "e_wo_entrp"),
        ],
    )
    def test_energy_convergence_is_what_the_old_trajectory_computed(
        self, relax, kind, old_key
    ):
        """|E_last - E| over the SCF steps of the run."""
        parsed, _, _ = relax
        with DataArchive.extract(
            TEST_FILES_DIR / "vasp" / "r2scan_relax.json.gz"
        ) as directory:
            calc, _ = Calculation.from_vasp_files(
                directory,
                "standard",
                vasprun_file="vasprun.xml.gz",
                outcar_file="OUTCAR.gz",
                contcar_file="CONTCAR.gz",
            )
        old = get_trajectories_from_calculations([calc])[0].convergence_data[old_key]
        new = parsed.trajectory.energy_convergence(kind)
        assert len(new) == 268
        np.testing.assert_allclose(new, old, atol=1e-12)
        assert new[-1] == 0.0

    def test_without_scf_steps_it_is_by_ionic_step(self, relax):
        row = TrajectoryRow(
            **{
                **relax[0].trajectory.model_dump(),
                "scf_energy": None,
                "scf_free_energy": None,
                "scf_energy_wo_entropy": None,
                "num_scf_steps": [0] * 6,
            }
        )
        convergence = row.energy_convergence()
        assert len(convergence) == 6 and convergence[-1] == 0.0

    def test_unknown_energy(self, relax):
        with pytest.raises(ValueError, match="Unknown kind"):
            relax[0].trajectory.energy_convergence("enthalpy")


class TestPmg:
    def test_structures(self, relax):
        parsed, vasprun, _ = relax
        structures = parsed.trajectory.structures
        assert len(structures) == 6
        for structure, step in zip(structures, vasprun.ionic_steps):
            assert structure.matches(step["structure"], scale=False)
            np.testing.assert_allclose(
                structure.frac_coords, step["structure"].frac_coords
            )

    def test_to_pmg(self, relax):
        parsed, vasprun, _ = relax
        trajectory = parsed.trajectory.to_pmg()
        assert len(trajectory) == 6
        last = trajectory.frame_properties[-1]
        np.testing.assert_allclose(last["forces"], vasprun.ionic_steps[-1]["forces"])
        np.testing.assert_allclose(last["stress"], vasprun.ionic_steps[-1]["stress"])
        assert last["energy"] == vasprun.ionic_steps[-1]["e_0_energy"]
        assert last["free_energy"] == vasprun.ionic_steps[-1]["e_fr_energy"]
        np.testing.assert_allclose(
            trajectory[-1].lattice.matrix,
            vasprun.ionic_steps[-1]["structure"].lattice.matrix,
        )

    def test_to_pmg_without_stress(self, fixed_cell):
        trajectory = fixed_cell[0].trajectory.to_pmg()
        assert "stress" not in trajectory.frame_properties[0]
        assert "forces" in trajectory.frame_properties[0]


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
class TestArrow:
    def test_schema(self):
        schema = pa.schema(arrowize(TrajectoryRow))
        for name in ("lattice", "frac_coords", "forces", "stress", "magmoms"):
            assert schema.field(name).type == pa.large_list(pa.float64()), name
        for name in ("energy", "free_energy", "max_force", "scf_energy"):
            assert schema.field(name).type == pa.list_(pa.float64()), name
        assert schema.field("num_scf_steps").type == pa.list_(pa.int64())
        assert schema.field("species").type == pa.list_(pa.string())
        assert schema.field("run_type").type == pa.string()
        # the convergence data is computed, and is not a column
        assert not {"has_full_output", "energy_convergence", "elements"} & set(
            schema.names
        )

    @pytest.mark.parametrize("fixture", ["relax", "fixed_cell", "unpolarized"])
    def test_roundtrip(self, fixture, request):
        row = request.getfixturevalue(fixture)[0].trajectory
        spec = PARSED_TABLES["trajectories"]
        schema = pa.schema(arrowize(TrajectoryRow))
        schema = pa.schema([schema.field(c) for c in spec.ordered_columns])
        table = pa.Table.from_pylist(
            [row.model_dump(context={"format": "arrow"})], schema=schema
        )
        restored = TrajectoryRow(**table.to_pylist(maps_as_pydicts="strict")[0])
        for name in TrajectoryRow.model_fields:
            before, after = getattr(row, name), getattr(restored, name)
            if isinstance(before, list) and before and isinstance(before[0], float):
                # doubles are stored as doubles
                np.testing.assert_array_equal(after, before)
        assert restored.spin_mode == row.spin_mode
        assert restored.max_force == row.max_force

    def test_written_options(self, relax):
        """Floats are not dictionary encoded, and only the filtered columns have statistics."""
        row = relax[0].trajectory
        spec = PARSED_TABLES["trajectories"]
        schema = pa.schema(arrowize(TrajectoryRow))
        schema = pa.schema([schema.field(c) for c in spec.ordered_columns])
        table = pa.Table.from_pylist(
            [row.model_dump(context={"format": "arrow"})], schema=schema
        )
        buffer = io.BytesIO()
        pq.write_table(table, buffer, compression="zstd", **spec.parquet_options)
        group = pq.ParquetFile(io.BytesIO(buffer.getvalue())).metadata.row_group(0)
        by_path = {
            group.column(i).path_in_schema: group.column(i)
            for i in range(group.num_columns)
        }

        for path in ("forces.list.element", "energy.list.element", "ediff"):
            assert not {"PLAIN_DICTIONARY", "RLE_DICTIONARY"} & set(
                by_path[path].encodings
            ), path
        assert by_path["identifier"].statistics.has_min_max
        assert by_path["ediff"].statistics.has_min_max
        statistics = by_path["forces.list.element"].statistics
        assert statistics is None or not statistics.has_min_max
