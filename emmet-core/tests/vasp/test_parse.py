"""Test the parsing of a calculation into the rows of the parsed tier."""

import gc
import os
import shutil
import sys
import time
import weakref
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from emmet.core import ARROW_COMPATIBLE
from emmet.core.band_theory import BSPathType, ElectronicBS
from emmet.core.io.pymatgen import Chgcar, Vasprun
from emmet.core.tasks import CoreTaskDoc
from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive, assert_nested_close
from emmet.core.types.enums import TaskState
from emmet.core.vasp.calc_types.enums import TaskType
from emmet.core.vasp.calculation import Calculation
from emmet.core.vasp.models import VOLUMETRIC_PARSERS, Pot
from emmet.core.vasp.parse import (
    DEFAULT_VOLUMETRIC_TYPES,
    DEFAULT_POLICY,
    NOT_PARSED_BY_DEFAULT_VOLUMETRIC_TYPES,
    DirectorySource,
    ParsePolicy,
    parse_calculation,
)
from emmet.core.vasp.parsed import (
    PARSED_TABLES,
    BandStructureProjectionsRow,
    BandStructureRow,
    DosProjectionsRow,
    DosRow,
    ParseOutcome,
    ChargeDensityRow,
)

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize

ID_1, ID_2, ID_3 = "aaaaaaab", "aaaaaaac", "aaaaaaad"


@pytest.fixture
def extract():
    """Extract a directory of VASP files, which can be changed by the test."""
    extracted = []

    def _extract(fixture: str):
        archive = DataArchive.extract(TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz")
        extracted.append(archive)
        return archive.__enter__()

    yield _extract
    for archive in extracted:
        archive.__exit__(None, None, None)


def sources(directory):
    return DirectorySource.from_directory(directory)


def parse(directory, identifier=ID_1, policy=DEFAULT_POLICY, **kwargs):
    """Parse the only calculation of a directory and all of its objects."""
    (source,) = sources(directory)
    parsed = parse_calculation(source, identifier, policy, **kwargs)
    return parsed, list(parsed.objects())


def tables(rows):
    return [table for table, _ in rows]


@pytest.fixture
def mark(monkeypatch):
    """Change the properties of the calculation which is parsed."""

    def _mark(**changes):
        original = Calculation._from_vasp_files.__func__

        def _from_vasp_files(cls, *args, **kwargs):
            calc, objects, vasprun = original(cls, *args, **kwargs)
            for key, value in changes.items():
                setattr(calc, key, value)
            return calc, objects, vasprun

        monkeypatch.setattr(
            Calculation, "_from_vasp_files", classmethod(_from_vasp_files)
        )

    return _mark


class TestPolicy:
    @pytest.mark.parametrize("task_type", list(TaskType))
    def test_mp_production_electronic_structure(self, task_type):
        wanted = task_type.value in {
            "Static",
            "NSCF Uniform",
            "NSCF Line",
            "SCF Line",
        }
        assert DEFAULT_POLICY.wants_dos(task_type) is wanted
        assert DEFAULT_POLICY.wants_bandstructure(task_type) is wanted

    def test_mp_production(self):
        assert DEFAULT_POLICY == ParsePolicy()
        assert DEFAULT_POLICY.volumetric_types == DEFAULT_VOLUMETRIC_TYPES
        assert not DEFAULT_POLICY.include_failed
        assert DEFAULT_POLICY.require_known_task_type
        assert (
            DEFAULT_POLICY.dos_projections and DEFAULT_POLICY.bandstructure_projections
        )
        # every volumetric type except CHG, which duplicates the CHGCAR, and POT,
        # a restart file whose potential is in the LOCPOT
        not_parsed = {"CHG", "POT"}
        assert not_parsed <= set(VOLUMETRIC_PARSERS)
        assert not_parsed == set(NOT_PARSED_BY_DEFAULT_VOLUMETRIC_TYPES)
        assert set(DEFAULT_VOLUMETRIC_TYPES) == set(VOLUMETRIC_PARSERS) - not_parsed
        for file_type in VOLUMETRIC_PARSERS:
            assert DEFAULT_POLICY.wants_volumetric(file_type) is (
                file_type not in not_parsed
            )
        # the files which are the point of the potential and the charge density are
        assert DEFAULT_POLICY.wants_volumetric("LOCPOT")
        assert DEFAULT_POLICY.wants_volumetric("CHGCAR")

    def test_task_types_can_be_configured(self):
        everything = ParsePolicy(dos_task_types=None, bandstructure_task_types=None)
        nothing = ParsePolicy(dos_task_types=(), bandstructure_task_types=())
        custom = ParsePolicy(dos_task_types=(TaskType.Deformation,))
        for task_type in TaskType:
            assert everything.wants_dos(task_type)
            assert everything.wants_bandstructure(task_type)
            assert not nothing.wants_dos(task_type)
            assert not nothing.wants_bandstructure(task_type)
        assert custom.wants_dos(TaskType.Deformation)
        assert not custom.wants_dos(TaskType.Static)
        # a calculation with no type is not any type
        assert not DEFAULT_POLICY.wants_dos(None) and everything.wants_dos(None)

    def test_volumetric_types(self):
        policy = ParsePolicy(volumetric_types=("chgcar", "LOCPOT"))
        assert policy.volumetric_types == ("CHGCAR", "LOCPOT")
        assert policy.wants_volumetric("CHGCAR") and policy.wants_volumetric("LOCPOT")
        assert not policy.wants_volumetric("AECCAR0")
        assert not ParsePolicy(volumetric_types=()).wants_volumetric("CHGCAR")

        # CHG and POT are not parsed by default, but can be asked for
        assert not ParsePolicy().wants_volumetric("CHG")
        assert not ParsePolicy().wants_volumetric("POT")
        assert ParsePolicy(volumetric_types=("chg", "pot")).wants_volumetric("POT")
        assert ParsePolicy(volumetric_types=("chg",)).wants_volumetric("CHG")
        assert ParsePolicy(
            volumetric_types=(*DEFAULT_VOLUMETRIC_TYPES, "CHG")
        ).wants_volumetric("CHG")
        # None is all of them
        everything = ParsePolicy(volumetric_types=None)
        assert all(everything.wants_volumetric(t) for t in VOLUMETRIC_PARSERS)

        with pytest.raises(ValidationError, match="Unknown volumetric file types"):
            ParsePolicy(volumetric_types=("CHGCAR", "WAVECAR"))

    @pytest.mark.parametrize(
        "completed, task_type, policy, outcome",
        [
            (TaskState.SUCCESS, TaskType.Static, {}, ParseOutcome.PARSED),
            (TaskState.FAILED, TaskType.Static, {}, ParseOutcome.SKIPPED_FAILED),
            (TaskState.ERROR, TaskType.Static, {}, ParseOutcome.SKIPPED_FAILED),
            (
                TaskState.SUCCESS,
                TaskType.Unrecognized,
                {},
                ParseOutcome.SKIPPED_UNRECOGNIZED,
            ),
            (
                TaskState.FAILED,
                TaskType.Unrecognized,
                {},
                ParseOutcome.SKIPPED_FAILED,
            ),
            (
                TaskState.FAILED,
                TaskType.Static,
                {"include_failed": True},
                ParseOutcome.PARSED,
            ),
            (
                TaskState.SUCCESS,
                TaskType.Unrecognized,
                {"require_known_task_type": False},
                ParseOutcome.PARSED,
            ),
            (
                TaskState.FAILED,
                TaskType.Unrecognized,
                {"include_failed": True},
                ParseOutcome.SKIPPED_UNRECOGNIZED,
            ),
        ],
    )
    def test_outcome(self, completed, task_type, policy, outcome):
        calc = SimpleNamespace(has_vasp_completed=completed, task_type=task_type)
        assert ParsePolicy(**policy).outcome(calc) == outcome


class TestParseCalculation:
    def test_nscf_uniform(self, extract):
        """A non-self-consistent calculation has electronic structure, split from its projections."""
        directory = extract("Si_uniform")
        parsed, rows = parse(directory, "mp-1")

        assert parsed.outcome == ParseOutcome.PARSED and parsed.errors == []
        # the electronic structure, and no volumetric data as there is none
        assert tables(rows) == [
            "total-dos",
            "projected-dos",
            "bandstructures",
            "projected-bandstructures",
        ]
        assert [type(row) for _, row in rows] == [
            DosRow,
            DosProjectionsRow,
            BandStructureRow,
            BandStructureProjectionsRow,
        ]
        for table, row in rows:
            assert type(row) is PARSED_TABLES[table].row_model

        # every row is described the same way as the task
        task = parsed.task
        assert task.task_type == TaskType.NSCF_Uniform
        assert task.formula_pretty == "Si" and task.chemsys == "Si"
        for _, row in rows:
            assert row.identifier == task.task_id == parsed.trajectory.identifier
            assert row.completed_at == task.completed_at == parsed.completed_at
            assert (row.year, row.month, row.day) == (
                task.completed_at.year,
                task.completed_at.month,
                task.completed_at.day,
            )
            assert row.run_type == task.run_type
            assert row.task_type == TaskType.NSCF_Uniform
            assert row.formula_pretty == "Si" and row.chemsys == "Si"

        # nothing about projections is stored with the total DOS and band structure
        by_table = dict(rows)
        assert by_table["total-dos"].take_projections() is None
        assert by_table["bandstructures"].take_projections() is None
        assert by_table["projected-bandstructures"].path_convention == (
            by_table["bandstructures"].path_convention
        )
        # a band structure on a mesh follows no path, which is not an unknown path
        assert by_table["bandstructures"].path_convention == BSPathType.uniform
        assert by_table["bandstructures"].kpoint_labels is None
        # the weights of the irreducible k-points of a mesh are kept, and make up the zone
        weights = by_table["bandstructures"].kpoint_weights
        assert len(weights) == len(by_table["bandstructures"].qpoints)
        assert sum(weights) == pytest.approx(1.0)

        # the objects are those of the vasprun
        vasprun = Vasprun(directory / "vasprun.xml.gz", parse_projected_eigen=True)
        dos = by_table["total-dos"].to_pmg(by_table["projected-dos"])
        assert dos.structure == vasprun.complete_dos.structure
        for spin, densities in vasprun.complete_dos.densities.items():
            assert np.allclose(dos.densities[spin], densities, rtol=1e-6)
        assert set(dos.pdos) == set(vasprun.complete_dos.pdos)

        band_structure = by_table["bandstructures"].to_pmg(
            by_table["projected-bandstructures"]
        )
        pmg_bs = vasprun.get_band_structure(efermi="smart")
        assert np.allclose(band_structure.efermi, pmg_bs.efermi)
        for spin, bands in pmg_bs.bands.items():
            assert np.allclose(band_structure.bands[spin], bands, atol=1e-6)
        assert band_structure.projections

        manifest = parsed.manifest_row()
        assert manifest.outcome == ParseOutcome.PARSED
        assert manifest.tables == tables(rows)
        assert manifest.errors == []
        assert manifest.task_type == TaskType.NSCF_Uniform

    def test_identifier_forms(self, extract):
        directory = extract("Si_uniform")
        for given, expected in (
            ("aaaaaaab", "aaaaaaab"),
            ("mp-aaaaaaab", "mp-aaaaaaab"),
            ("mp-1", "mp-aaaaaaab"),
            ("1", "aaaaaaab"),
        ):
            (source,) = sources(directory)
            parsed = parse_calculation(
                source,
                given,
                ParsePolicy(dos_task_types=(), bandstructure_task_types=()),
            )
            assert parsed.identifier == parsed.task.task_id == expected
            assert parsed.trajectory.identifier == expected
            assert parsed.manifest_row().identifier == expected

        with pytest.raises(ValidationError):
            parse_calculation(source, "not an identifier!")

    def test_calculation_not_a_static_run_has_only_volumetric_data(self, extract):
        """A structure optimization is not given electronic structure by the default policy."""
        directory = extract("Si_static")
        parsed, rows = parse(directory)

        assert parsed.task.task_type == TaskType.Structure_Optimization
        assert tables(rows) == ["charge-density"]
        row = rows[0][1]
        assert isinstance(row, ChargeDensityRow)
        assert row.file_name == "CHGCAR.gz"
        assert row.spin_mode.value == "collinear"
        assert row.run_type == parsed.task.run_type
        # the structure in a CHGCAR is the one it was written for, not necessarily the final one
        assert row.structure.composition == parsed.task.structure.composition

        # the volumetric data is that of the file
        pmg_chgcar = Chgcar.from_file(str(directory / "CHGCAR.gz"))
        assert np.allclose(
            row.to_pmg(pmg_cls=Chgcar).data["total"], pmg_chgcar.data["total"]
        )
        # the settings which explain the data are on the row
        assert parsed._parameters["LVTOT"] is True

    def test_policy_selects_objects(self, extract):
        directory = extract("Si_static")

        def objects(**policy):
            _, rows = parse(directory, policy=ParsePolicy(**policy))
            return tables(rows)

        everything = {"dos_task_types": None, "bandstructure_task_types": None}
        assert "charge-density" in objects(**everything)
        assert objects(**everything)[:2] == ["total-dos", "projected-dos"]
        assert "bandstructures" in objects(**everything)

        assert "charge-density" not in objects(volumetric_types=())
        assert "charge-density" not in objects(volumetric_types=("LOCPOT",))
        assert objects(volumetric_types=("CHGCAR",)) == ["charge-density"]

        # projections are optional, the DOS and band structure are not
        no_projections = objects(
            dos_projections=False, bandstructure_projections=False, **everything
        )
        assert "projected-dos" not in no_projections
        assert "projected-bandstructures" not in no_projections
        assert {"total-dos", "bandstructures"} <= set(no_projections)

        assert objects(dos_task_types=None, bandstructure_task_types=()) == [
            "total-dos",
            "projected-dos",
            "charge-density",
        ]

    def test_chg_is_not_parsed_by_default(self, extract):
        directory = extract("Si_static")
        shutil.copy(directory / "CHGCAR.gz", directory / "CHG.gz")
        wanted = {"charge-density", "charge-density-chg"}

        def volumetric_tables(**policy):
            _, rows = parse(directory, policy=ParsePolicy(**policy))
            return [t for t in tables(rows) if t in wanted]

        # a CHG next to a CHGCAR does not make a second charge density
        assert volumetric_tables() == ["charge-density"]
        # but it can be asked for, and has a table of its own
        assert sorted(volumetric_tables(volumetric_types=("CHGCAR", "CHG"))) == [
            "charge-density",
            "charge-density-chg",
        ]
        assert sorted(volumetric_tables(volumetric_types=None)) == [
            "charge-density",
            "charge-density-chg",
        ]

    def test_pot_is_not_parsed_by_default(self, extract, tmp_path):
        directory = extract("Si_static")

        # a spin-polarized POT: two blocks of potential with augmentation data
        chgcar = Chgcar.from_file(str(directory / "CHGCAR.gz"))
        grid = chgcar.data["total"]
        pot = Pot(
            chgcar.structure,
            {"total": grid, "diff": -grid},
            data_aug={"total": {}, "diff": {}},
        )
        pot.write_file(directory / "POT")

        def volumetric_rows(**policy):
            _, rows = parse(directory, policy=ParsePolicy(**policy))
            wanted = {"local-potential-pot", "charge-density", "local-potential"}
            return {t: row for t, row in rows if t in wanted}

        # a POT next to a CHGCAR is not parsed with it by default
        assert set(volumetric_rows()) == {"charge-density"}

        # but can be asked for, and its blocks are spin-up and spin-down
        rows = volumetric_rows(volumetric_types=("CHGCAR", "POT"))
        assert set(rows) == {"charge-density", "local-potential-pot"}
        potential = rows["local-potential-pot"]
        # its blocks are the potentials of the two spins, and are not a total and a magnetization
        assert [
            c for c in potential.BLOCK_COLUMNS if getattr(potential, c) is not None
        ] == [
            "spin_up",
            "spin_down",
        ]
        assert potential.file_name == "POT"
        charge = rows["charge-density"]
        assert [c for c in charge.BLOCK_COLUMNS if getattr(charge, c) is not None] == [
            "total",
            "magnetization",
        ]

    def test_multi_calculation_directory(self, extract):
        """Each calculation of a directory is parsed by itself, and has its own row."""
        directory = extract("Si_old_double_relax")
        sources_ = sources(directory)
        assert [s.calc_suffix for s in sources_] == ["relax1", "relax2"]

        parsed = [
            parse_calculation(source, ident, batch_id="batch-1", tags=["a"])
            for source, ident in zip(sources_, (ID_1, ID_2))
        ]
        relax1, relax2 = (p.task for p in parsed)

        # the calculations of a directory share a location and are told apart by suffix
        assert relax1.dir_name == relax2.dir_name == sources_[0].dir_name
        assert (relax1.calc_suffix, relax2.calc_suffix) == ("relax1", "relax2")
        assert (relax1.task_id, relax2.task_id) == (ID_1, ID_2)
        assert relax1.batch_id == "batch-1" and "a" in relax1.tags

        # the original inputs are the first calculation's, and not guessed for the second
        assert relax1.orig_inputs is not None
        assert relax1.orig_inputs.incar is not None
        assert relax1.orig_inputs.kpoints is not None
        assert relax2.orig_inputs is None

        # each calculation has its own results
        assert relax1.input.incar != relax2.input.incar
        assert relax1.completed_at != relax2.completed_at
        assert parsed[0].trajectory.identifier == ID_1
        assert parsed[1].trajectory.identifier == ID_2
        assert len(parsed[0].trajectory.energy) != 0

        # the manifest can tell calculations of a directory apart
        manifests = [p.manifest_row() for p in parsed]
        assert {m.dir_name for m in manifests} == {relax1.dir_name}
        assert [m.calc_suffix for m in manifests] == ["relax1", "relax2"]

        # relaxations have no electronic structure in the default policy, but can
        for p in parsed:
            assert list(p.objects()) == []
        for source, ident in zip(sources_, (ID_1, ID_2)):
            rows = list(
                parse_calculation(
                    source, ident, ParsePolicy(dos_task_types=None)
                ).objects()
            )
            assert "total-dos" in tables(rows)

    def test_completion_time_comes_from_the_source(self, extract):
        """The time that partitions rows is supplied by the source, not read from files."""
        directory = extract("Si_uniform")
        (source,) = sources(directory)
        completed_at = datetime(2021, 6, 30, 23, 59, 59, tzinfo=UTC)

        class ArchivedSource:
            files = source.files
            dir_name = "archive:7f5a7f14"
            calc_suffix = "standard"

        ArchivedSource.completed_at = completed_at
        parsed = parse_calculation(ArchivedSource, ID_1)
        rows = list(parsed.objects())
        assert parsed.task.completed_at == completed_at
        assert parsed.task.dir_name == "archive:7f5a7f14"
        assert parsed.manifest_row().completed_at == completed_at
        assert rows
        for _, row in rows:
            assert row.completed_at == completed_at
            assert (row.year, row.month, row.day) == (2021, 6, 30)

    @pytest.mark.skipif(sys.platform == "win32", reason="requires tzset")
    @pytest.mark.parametrize("zone", ["UTC", "America/Los_Angeles", "Asia/Tokyo"])
    def test_completion_time_does_not_depend_on_the_time_zone(
        self, extract, monkeypatch, zone
    ):
        directory = extract("Si_uniform")
        expected = datetime(2020, 12, 31, 23, 30, tzinfo=UTC)
        for path in directory.glob("vasprun.xml*"):
            os.utime(path, (expected.timestamp(), expected.timestamp()))

        monkeypatch.setenv("TZ", zone)
        time.tzset()
        try:
            (source,) = sources(directory)
            assert source.completed_at == expected
            parsed, rows = parse(directory, policy=ParsePolicy())
            assert parsed.task.completed_at == expected
            # late in the evening in Los Angeles is still the same date for everyone
            for _, row in rows:
                assert (row.year, row.month, row.day) == (2020, 12, 31)
        finally:
            monkeypatch.undo()
            time.tzset()


class TestSkippedCalculations:
    @pytest.mark.parametrize(
        "changes, outcome",
        [
            ({"has_vasp_completed": TaskState.FAILED}, ParseOutcome.SKIPPED_FAILED),
            ({"task_type": TaskType.Unrecognized}, ParseOutcome.SKIPPED_UNRECOGNIZED),
        ],
    )
    def test_skipped(self, extract, mark, changes, outcome):
        """Large objects are skipped, but the calculation is still recorded."""
        directory = extract("Si_uniform")
        mark(**changes)
        parsed, rows = parse(directory)

        assert parsed.outcome == outcome
        assert rows == []
        # the task and trajectory are not expensive, and are kept
        assert isinstance(parsed.task, CoreTaskDoc) and parsed.task.task_id == ID_1
        assert parsed.trajectory is not None
        manifest = parsed.manifest_row()
        assert manifest.outcome == outcome
        assert manifest.tables == [] and manifest.errors == []
        assert manifest.dir_name == parsed.task.dir_name

    def test_failed_calculations_can_be_included(self, extract, mark):
        directory = extract("Si_uniform")
        mark(has_vasp_completed=TaskState.FAILED)
        parsed, rows = parse(directory, policy=ParsePolicy(include_failed=True))
        assert parsed.outcome == ParseOutcome.PARSED
        assert "total-dos" in tables(rows)

    def test_unrecognized_calculations_can_be_included(self, extract, mark):
        directory = extract("Si_static")
        mark(task_type=TaskType.Unrecognized)
        parsed, rows = parse(
            directory, policy=ParsePolicy(require_known_task_type=False)
        )
        assert parsed.outcome == ParseOutcome.PARSED
        # volumetric data is kept whatever the type, but there is no electronic structure
        assert tables(rows) == ["charge-density"]


class TestErrors:
    def test_missing_files(self, extract):
        directory = extract("Si_uniform")
        (directory / "OUTCAR.gz").unlink()
        (source,) = sources(directory)
        parsed = parse_calculation(source, ID_1)

        assert parsed.outcome == ParseOutcome.ERROR
        assert parsed.task is None and parsed.trajectory is None
        assert isinstance(parsed.exception, FileNotFoundError)
        assert list(parsed.objects()) == []

        manifest = parsed.manifest_row()
        assert manifest.outcome == ParseOutcome.ERROR
        assert manifest.tables == []
        assert "OUTCAR" in manifest.errors[0]
        # what is known about the calculation is recorded
        assert manifest.identifier == ID_1
        assert manifest.calc_suffix == "standard"
        assert manifest.dir_name == source.dir_name
        assert manifest.completed_at == source.completed_at

    def test_unreadable_vasprun(self, extract):
        directory = extract("Si_uniform")
        (directory / "vasprun.xml.gz").write_bytes(b"this is not a vasprun")
        parsed, rows = parse(directory)
        assert parsed.outcome == ParseOutcome.ERROR
        assert parsed.task is None and rows == []
        assert parsed.manifest_row().errors

    def test_error_does_not_stop_other_calculations(self, extract):
        directory = extract("Si_old_double_relax")
        (directory / "OUTCAR.relax1.gz").unlink()
        relax1, relax2 = (
            parse_calculation(source, ident)
            for source, ident in zip(sources(directory), (ID_1, ID_2))
        )
        assert relax1.outcome == ParseOutcome.ERROR
        assert relax2.outcome == ParseOutcome.PARSED and relax2.task is not None

    def test_one_bad_object_does_not_affect_the_others(self, extract):
        directory = extract("Si_static")
        shutil.copy(directory / "CHGCAR.gz", directory / "AECCAR0.gz")
        shutil.copy(directory / "CHGCAR.gz", directory / "LOCPOT.gz")
        (directory / "CHGCAR.gz").write_bytes(b"not a CHGCAR")

        parsed, rows = parse(directory)
        assert parsed.outcome == ParseOutcome.PARSED
        assert sorted(tables(rows)) == ["core-density", "local-potential"]
        assert len(parsed.errors) == 1 and "CHGCAR.gz" in parsed.errors[0]

        manifest = parsed.manifest_row()
        assert sorted(manifest.tables) == ["core-density", "local-potential"]
        assert manifest.errors == parsed.errors
        assert manifest.outcome == ParseOutcome.PARSED

    def test_bad_density_of_states_does_not_affect_band_structure(
        self, extract, monkeypatch
    ):
        directory = extract("Si_uniform")

        def fail(*args, **kwargs):
            raise RuntimeError("no DOS")

        monkeypatch.setattr(DosRow, "from_pmg", classmethod(fail))
        parsed, rows = parse(directory)
        assert tables(rows) == ["bandstructures", "projected-bandstructures"]
        assert "density of states" in parsed.errors[0] and "no DOS" in parsed.errors[0]


class TestLaziness:
    @pytest.fixture
    def two_volumetric_files(self, extract):
        directory = extract("Si_static")
        shutil.copy(directory / "CHGCAR.gz", directory / "AECCAR0.gz")
        shutil.copy(directory / "CHGCAR.gz", directory / "AECCAR1.gz")
        return directory

    @pytest.fixture
    def parser_calls(self, monkeypatch):
        """Record every time a volumetric file is read, and call `on_read` if set."""

        class Calls(list):
            on_read = None
            parsed_objects: list[weakref.ref] = []

        calls = Calls()
        calls.parsed_objects = []
        for file_type, cls in list(VOLUMETRIC_PARSERS.items()):

            class Recording(cls):  # type: ignore[valid-type, misc]
                @classmethod
                def from_file(cls_, filename, *args, **kwargs):
                    calls.append(os.path.basename(filename))
                    if calls.on_read is not None:
                        calls.on_read(filename)
                    pmg_object = super().from_file(filename, *args, **kwargs)
                    calls.parsed_objects.append(weakref.ref(pmg_object))
                    return pmg_object

            monkeypatch.setitem(VOLUMETRIC_PARSERS, file_type, Recording)
        return calls

    def test_nothing_is_parsed_until_it_is_asked_for(
        self, two_volumetric_files, parser_calls
    ):
        (source,) = sources(two_volumetric_files)
        parsed = parse_calculation(source, ID_1)
        assert parsed.task is not None
        assert parser_calls == []

        objects = parsed.objects()
        assert parser_calls == []
        _, first = next(objects)
        assert len(parser_calls) == 1
        _, second = next(objects)
        assert len(parser_calls) == 2
        assert {first.file_name, second.file_name} <= {
            "AECCAR0.gz",
            "AECCAR1.gz",
            "CHGCAR.gz",
        }
        assert first.file_name != second.file_name
        assert len(list(objects)) == 1
        assert len(parser_calls) == 3

    def test_objects_are_freed_before_the_next_file_is_read(
        self, two_volumetric_files, parser_calls
    ):
        """Only one volumetric row is in memory at a time, which is the point of
        making them lazily: when the consumer lets go of one, the generator must
        not be holding it while it reads the next file."""
        (source,) = sources(two_volumetric_files)
        parsed = parse_calculation(source, ID_1)
        objects = parsed.objects()

        previous: list[weakref.ref] = []
        alive_when_reading: list[bool] = []

        def on_read(filename):
            gc.collect()
            alive_when_reading.append(bool(previous) and previous[-1]() is not None)

        parser_calls.on_read = on_read
        parsed_object_alive: list[bool] = []
        for _, row in objects:
            # the pymatgen object the row was made from is not kept with the row
            gc.collect()
            parsed_object_alive.append(parser_calls.parsed_objects[-1]() is not None)
            previous.append(weakref.ref(row))
            del row

        assert len(alive_when_reading) == 3
        assert alive_when_reading == [False, False, False]
        assert parsed_object_alive == [False, False, False]

    def test_the_vasprun_is_freed_after_the_density_of_states(self, extract):
        directory = extract("Si_uniform")
        (source,) = sources(directory)
        parsed = parse_calculation(source, ID_1)
        assert parsed._vasprun is not None

        objects = parsed.objects()
        reference = weakref.ref(parsed._vasprun)
        # the parsed calculation lets go of it as soon as the objects are made...
        table, row = next(objects)
        assert table == "total-dos" and parsed._vasprun is None
        del row
        next(objects)  # projected-dos
        # ...and so does the generator, before the band structure is read
        gc.collect()
        assert reference() is None
        assert tables(list(objects)) == ["bandstructures", "projected-bandstructures"]

    def test_vasprun_is_only_kept_if_it_is_needed(self, extract, mark):
        directory = extract("Si_static")
        (source,) = sources(directory)

        # no density of states or band structure for a structure optimization
        parsed = parse_calculation(source, ID_1)
        assert parsed._vasprun is None and parsed._bandstructure_input is None

        # the density of states needs the vasprun, and the band structure its file
        wanted = parse_calculation(
            source,
            ID_1,
            ParsePolicy(dos_task_types=None, bandstructure_task_types=None),
        )
        assert wanted._vasprun is not None
        assert wanted._bandstructure_input is not None

        only_bs = parse_calculation(
            source, ID_1, ParsePolicy(bandstructure_task_types=None)
        )
        assert only_bs._vasprun is None and only_bs._bandstructure_input is not None

        # a skipped calculation has no use for either
        mark(has_vasp_completed=TaskState.FAILED)
        skipped = parse_calculation(
            source,
            ID_1,
            ParsePolicy(dos_task_types=None, bandstructure_task_types=None),
        )
        assert skipped.outcome == ParseOutcome.SKIPPED_FAILED
        assert skipped._vasprun is None and skipped._bandstructure_input is None

    def test_objects_can_only_be_iterated_once(self, extract):
        directory = extract("Si_uniform")
        (source,) = sources(directory)
        parsed = parse_calculation(source, ID_1)
        assert len(list(parsed.objects())) == 4
        with pytest.raises(RuntimeError, match="only be parsed once"):
            list(parsed.objects())

    def test_manifest_is_complete_after_all_objects(self, extract):
        directory = extract("Si_uniform")
        (source,) = sources(directory)
        parsed = parse_calculation(source, ID_1)
        objects = parsed.objects()
        assert parsed.manifest_row().tables == []
        next(objects)
        assert parsed.manifest_row().tables == ["total-dos"]
        list(objects)
        assert len(parsed.manifest_row().tables) == 4


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
class TestLocpotIsReadOnce:
    """The LOCPOT is read for the averages of the task and for its row, which share one read."""

    @pytest.fixture
    def reads(self, monkeypatch):
        """The names of the files read as volumetric data, by whichever class reads them.

        Every reader, including the subclasses of emmet, ends up in the `__init__` of
        `VolumetricData` after reading, so this counts the files read, not who read them.
        """
        from pymatgen.io.vasp import Locpot

        calls: list[str] = []
        original = Locpot.from_file.__func__

        def counted(cls_, filename, *args, **kwargs):
            calls.append(os.path.basename(str(filename)))
            return original(cls_, filename, *args, **kwargs)

        monkeypatch.setattr(Locpot, "from_file", classmethod(counted))
        return calls

    @pytest.fixture
    def directory(self, extract):
        return extract("magnetic_static_volumetric")

    def locpot_reads(self, calls):
        return [c for c in calls if c.startswith("LOCPOT")]

    def test_the_averages_and_the_row_are_from_one_read(self, directory, reads):
        parsed, rows = parse(directory)
        assert "local-potential" in tables(rows)
        assert parsed.task.output.locpot is not None
        assert self.locpot_reads(reads) == ["LOCPOT.gz"]

    def test_the_averages_only(self, directory, reads):
        """The policy does not keep the LOCPOT as a row, so what was read is not kept."""
        policy = ParsePolicy(volumetric_types=("CHGCAR",))
        (source,) = sources(directory)
        parsed = parse_calculation(source, ID_1, policy)
        assert parsed.task.output.locpot is not None
        # it is not held for a row that will not be made
        assert parsed._locpot is None
        rows = list(parsed.objects())
        assert "local-potential" not in tables(rows)
        assert self.locpot_reads(reads) == ["LOCPOT.gz"]

    def test_the_row_only(self, directory, reads):
        parsed, rows = parse(directory, policy=ParsePolicy(average_locpot=False))
        assert "local-potential" in tables(rows)
        assert parsed.task.output.locpot is None
        assert self.locpot_reads(reads) == ["LOCPOT.gz"]

    def test_neither(self, directory, reads):
        policy = ParsePolicy(average_locpot=False, volumetric_types=("CHGCAR",))
        parsed, rows = parse(directory, policy=policy)
        assert parsed.task.output.locpot is None and self.locpot_reads(reads) == []

    def test_a_skipped_calculation_keeps_nothing(self, directory, reads, mark):
        mark(has_vasp_completed=TaskState.FAILED)
        (source,) = sources(directory)
        parsed = parse_calculation(source, ID_1)
        assert parsed.outcome == ParseOutcome.SKIPPED_FAILED
        assert parsed._locpot is None and list(parsed.objects()) == []
        assert self.locpot_reads(reads) == ["LOCPOT.gz"]

    def test_the_averages_are_those_of_the_calculation(self, directory):
        """What `Calculation.from_vasp_files` gives, which reads the file for itself."""
        parsed, _ = parse(directory)
        (source,) = sources(directory)
        calc, _ = Calculation.from_vasp_files(
            directory,
            "standard",
            vasprun_file="vasprun.xml.gz",
            outcar_file="OUTCAR.gz",
            contcar_file="CONTCAR.gz",
            volumetric_files=["LOCPOT.gz"],
        )
        assert parsed.task.output.locpot == calc.output.locpot
        # the averages are of the spin-up potential
        up = VOLUMETRIC_PARSERS["LOCPOT"].from_file(str(directory / "LOCPOT.gz"))
        np.testing.assert_allclose(
            parsed.task.output.locpot["0"], up.data["spin_up"].mean(axis=(1, 2))
        )
        assert not np.allclose(
            parsed.task.output.locpot["0"], up.data["spin_down"].mean(axis=(1, 2))
        )

    def test_the_row_is_the_same_as_that_of_a_read_of_its_own(self, directory):
        _, shared = parse(directory)
        _, own = parse(directory, policy=ParsePolicy(average_locpot=False))
        assert tables(shared) == tables(own)
        a, b = dict(shared)["local-potential"], dict(own)["local-potential"]
        assert a.model_dump() == b.model_dump()

    def test_the_rows_come_in_their_usual_order(self, directory):
        _, shared = parse(directory)
        _, own = parse(directory, policy=ParsePolicy(average_locpot=False))
        assert tables(shared) == tables(own)
        assert tables(shared).index("total-dos") < tables(shared).index(
            "local-potential"
        )

    def test_it_is_released_after_its_row_is_made(self, directory, monkeypatch):
        refs: list[weakref.ref] = []
        cls = VOLUMETRIC_PARSERS["LOCPOT"]

        class Recording(cls):  # type: ignore[valid-type, misc]
            @classmethod
            def from_file(cls_, filename, *args, **kwargs):
                pmg_object = super().from_file(filename, *args, **kwargs)
                refs.append(weakref.ref(pmg_object))
                return pmg_object

        monkeypatch.setitem(VOLUMETRIC_PARSERS, "LOCPOT", Recording)
        (source,) = sources(directory)
        parsed = parse_calculation(source, ID_1)
        # held until its row is made
        gc.collect()
        assert len(refs) == 1 and refs[0]() is not None
        objects = parsed.objects()
        for table, row in objects:
            if table == "local-potential":
                break
        del row
        gc.collect()
        assert refs[0]() is None


def test_rows_fit_their_tables(extract):
    """Every row can be written to the table it was made for, and read back."""
    directories = [extract("Si_uniform"), extract("Si_static")]
    policy = ParsePolicy(dos_task_types=None, bandstructure_task_types=None)

    seen = set()
    for i, directory in enumerate(directories):
        (source,) = sources(directory)
        parsed = parse_calculation(source, f"aaaaaaa{'bc'[i]}", policy)
        rows = list(parsed.objects())
        manifest_row = parsed.manifest_row()
        rows.append(("manifest", manifest_row))

        for table, row in rows:
            spec = PARSED_TABLES[table]
            assert type(row) is spec.row_model
            schema = pa.schema(arrowize(spec.row_model))
            arrow_table = pa.Table.from_pylist(
                [row.model_dump(context={"format": "arrow"})], schema=schema
            )
            assert arrow_table.schema == schema
            restored = spec.row_model(
                **arrow_table.to_pylist(maps_as_pydicts="strict")[0]
            )
            assert restored.identifier == row.identifier
            if table != "manifest":
                assert_nested_close(restored, row)
                assert set(spec.partition_by) <= set(arrow_table.column_names)
            seen.add(table)

    assert seen >= {
        "total-dos",
        "projected-dos",
        "bandstructures",
        "charge-density",
        "manifest",
    }


class TestCoreTaskDoc:
    """CoreTaskDoc.from_directory and from_calculation."""

    def test_from_directory(self, extract):
        directory = extract("Si_uniform")
        doc, trajectory = CoreTaskDoc.from_directory(directory, batch_id="batch-1")
        assert doc.calc_suffix == "standard"
        assert doc.task_type == TaskType.NSCF_Uniform
        assert doc.orig_inputs is not None and doc.batch_id == "batch-1"
        assert doc.completed_at.tzinfo is not None

        # it is the same document that parsing the calculation makes
        parsed = parse_calculation(*sources(directory), ID_1, batch_id="batch-1")
        for field in ("input", "output", "orig_inputs", "task_type", "run_type"):
            assert getattr(doc, field) == getattr(parsed.task, field)

    def test_multi_calculation_directory_needs_a_suffix(self, extract):
        directory = extract("Si_old_double_relax")
        with pytest.raises(ValueError, match="calc_suffix") as error:
            CoreTaskDoc.from_directory(directory)
        assert "relax1" in str(error.value) and "relax2" in str(error.value)

        relax1, _ = CoreTaskDoc.from_directory(directory, calc_suffix="relax1")
        relax2, trajectory = CoreTaskDoc.from_directory(directory, calc_suffix="relax2")
        assert (relax1.calc_suffix, relax2.calc_suffix) == ("relax1", "relax2")
        assert relax1.orig_inputs is not None and relax2.orig_inputs is None
        assert relax1.dir_name == relax2.dir_name
        assert len(trajectory.energy) > 0

        with pytest.raises(ValueError, match="calc_suffix"):
            CoreTaskDoc.from_directory(directory, calc_suffix="relax9")

    def test_a_single_suffixed_calculation_is_the_default(self, extract):
        directory = extract("Si_old_double_relax")
        for path in directory.glob("*.relax1.gz"):
            path.unlink()
        doc, _ = CoreTaskDoc.from_directory(directory)
        assert doc.calc_suffix == "relax2"

    def test_no_calculation(self, tmp_path):
        with pytest.raises(ValueError, match="none"):
            CoreTaskDoc.from_directory(tmp_path)


class TestBandStructureModes:
    """How the band structure is read depends on the kind of calculation."""

    @pytest.fixture
    def record_reads(self, monkeypatch):
        """Record how the band structure is read, instead of reading it."""
        import emmet.core.vasp.calculation as calculation_module

        reads: list[dict] = []
        fail_line_mode = {"fail": False}
        real = calculation_module.BSVasprun

        class RecordingBSVasprun:
            def __init__(self, filename, parse_projected_eigen=False, **kwargs):
                self.vasprun = real(
                    filename, parse_projected_eigen=parse_projected_eigen
                )
                self.parse_projected_eigen = parse_projected_eigen

            def get_band_structure(self, **kwargs):
                reads.append({"projected": self.parse_projected_eigen, **kwargs})
                if kwargs.get("line_mode") and fail_line_mode["fail"]:
                    raise RuntimeError("no band structure along symmetry lines")
                kwargs.pop("line_mode", None)
                kwargs.pop("kpoints_filename", None)
                return self.vasprun.get_band_structure(**kwargs)

        monkeypatch.setattr(calculation_module, "BSVasprun", RecordingBSVasprun)
        return reads, fail_line_mode

    def retype(self, monkeypatch, task_type):
        """Make the calculation, which is of one type, a calculation of another."""
        import emmet.core.vasp.parse as parse_module

        real_from_calculation = parse_module.CoreTaskDoc.from_calculation

        def from_calculation(*args, **kwargs):
            task = real_from_calculation(*args, **kwargs)
            task.task_type = task_type
            return task

        monkeypatch.setattr(
            parse_module.CoreTaskDoc, "from_calculation", from_calculation
        )

    def band_structure_row(self, directory):
        parsed, rows = parse(directory)
        return parsed, dict(rows).get("bandstructures")

    @pytest.mark.parametrize(
        "task_type, line_mode, strict",
        [
            (TaskType.SCF_Line, True, True),
            (TaskType.NSCF_Line, True, False),
        ],
    )
    def test_line_calculations_are_read_along_their_path(
        self, extract, monkeypatch, record_reads, task_type, line_mode, strict
    ):
        reads, _ = record_reads
        directory = extract("Si_uniform")
        self.retype(monkeypatch, task_type)
        parsed, row = self.band_structure_row(directory)
        assert parsed.errors == []

        (read,) = reads
        assert read["line_mode"] is True and read["projected"] is True
        # the KPOINTS of the calculation is used, not one found next to the vasprun
        assert (
            Path(read["kpoints_filename"]).resolve()
            == (directory / "KPOINTS.gz").resolve()
        )
        assert row is not None

    @pytest.mark.parametrize("task_type", [TaskType.Static, TaskType.NSCF_Uniform])
    def test_mesh_calculations_are_labelled_uniform(
        self, extract, monkeypatch, record_reads, task_type
    ):
        reads, _ = record_reads
        directory = extract("Si_uniform")
        self.retype(monkeypatch, task_type)
        parsed, row = self.band_structure_row(directory)
        assert parsed.errors == []

        # the mode is not forced for these, it is inferred from the INCAR as for a TaskDoc
        assert reads
        # whatever the way it was read, a band structure on a mesh follows no path
        assert row is not None and row.path_convention == BSPathType.uniform

    def test_a_failed_scf_line_is_an_error_and_not_another_band_structure(
        self, extract, monkeypatch, record_reads
    ):
        reads, fail = record_reads
        fail["fail"] = True
        directory = extract("Si_uniform")
        self.retype(monkeypatch, TaskType.SCF_Line)
        parsed, rows = parse(directory)

        assert "bandstructures" not in tables(rows)
        assert "projected-bandstructures" not in tables(rows)
        assert any("band structure" in err for err in parsed.errors)
        # the rest of the calculation is not affected
        assert "total-dos" in tables(rows)
        # there is no second attempt on all of the calculation's k-points
        assert [read.get("line_mode") for read in reads] == [True]

    def test_a_failed_nscf_line_is_read_on_its_k_points(
        self, extract, monkeypatch, record_reads
    ):
        reads, fail = record_reads
        fail["fail"] = True
        directory = extract("Si_uniform")
        self.retype(monkeypatch, TaskType.NSCF_Line)
        parsed, rows = parse(directory)

        assert parsed.errors == []
        assert [read.get("line_mode") for read in reads] == [True, None]
        by_table = dict(rows)
        # the path of a line calculation is not a mesh: it is not known
        assert by_table["bandstructures"].path_convention != BSPathType.uniform
        assert by_table["projected-bandstructures"].path_convention == (
            by_table["bandstructures"].path_convention
        )

    def test_projections_row_follows_the_band_structure(self, extract):
        directory = extract("Si_uniform")
        _, rows = parse(directory)
        by_table = dict(rows)
        assert by_table["projected-bandstructures"].path_convention == (
            BSPathType.uniform
        )

    def test_calculation_keeps_inferring_the_mode(self, extract, record_reads):
        """Called as `Calculation` does, the reader behaves as it did before."""
        from emmet.core.vasp.calculation import _parse_bandstructure_file

        reads, _ = record_reads
        directory = extract("Si_uniform")
        vasprun = directory / "vasprun.xml.gz"

        band_structure = _parse_bandstructure_file(
            "auto", vasprun, {"NSW": 0, "ICHARG": 11}, use_emmet_models=True
        )
        # an NSCF calculation is tried as line mode, without a KPOINTS file given
        assert [read.get("line_mode") for read in reads][0] is True
        assert "kpoints_filename" in reads[0] and reads[0]["kpoints_filename"] is None
        assert isinstance(band_structure, ElectronicBS)
        # a path convention is inferred, and is never `uniform`
        assert band_structure.path_convention != BSPathType.uniform


class TestSCFLine:
    """A self-consistent r2SCAN band structure: a weighted mesh, then a path of zero-weight k-points."""

    @pytest.fixture
    def scf_line(self, extract):
        if not (TEST_FILES_DIR / "vasp" / "r2scan_scf_line.json.gz").exists():
            pytest.skip("The SCF Line test file is not available.")
        directory = extract("r2scan_scf_line")
        parsed, rows = parse(directory)
        return directory, parsed, dict(rows)

    def test_the_calculation_is_an_scf_line(self, scf_line):
        _, parsed, _ = scf_line
        assert parsed.header.task_type == TaskType.SCF_Line
        assert parsed.header.run_type.value == "r2SCAN"
        assert parsed.errors == [] and parsed.outcome == ParseOutcome.PARSED

    def test_electronic_structure_is_kept(self, scf_line):
        _, _, rows = scf_line
        assert {
            "total-dos",
            "projected-dos",
            "bandstructures",
            "projected-bandstructures",
        } <= set(rows)

    def test_only_the_path_is_the_band_structure(self, scf_line):
        directory, _, rows = scf_line
        vasprun = Vasprun(directory / "vasprun.xml.gz")
        weights = np.array(vasprun.actual_kpoints_weights)
        n_path = int((weights == 0).sum())
        assert 0 < n_path < len(weights)
        # the path follows the mesh
        assert np.all(weights[-n_path:] == 0) and np.all(weights[:-n_path] > 0)

        band_structure = rows["bandstructures"]
        assert len(band_structure.qpoints) == n_path
        # k-points of the mesh are not in it
        mesh = np.array(vasprun.actual_kpoints)[: len(weights) - n_path]
        path = np.array(band_structure.qpoints)
        assert not any(
            np.allclose(path[0], kpt) and w > 0 for kpt, w in zip(mesh, weights)
        )
        assert np.allclose(path, np.array(vasprun.actual_kpoints)[-n_path:])

    def test_it_has_a_path_convention_and_labels(self, scf_line):
        _, _, rows = scf_line
        band_structure = rows["bandstructures"]
        assert band_structure.path_convention not in (
            BSPathType.unknown,
            BSPathType.uniform,
        )
        assert any(rows["bandstructures"].kpoint_labels)
        assert rows["projected-bandstructures"].path_convention == (
            band_structure.path_convention
        )

    def test_projections_are_of_the_path(self, scf_line):
        _, _, rows = scf_line
        n_bands, n_kpts, _, _ = rows["projected-bandstructures"].shape
        assert (n_bands, n_kpts) == tuple(rows["bandstructures"].shape)
        assert n_kpts == len(rows["bandstructures"].qpoints)
        # the path has no weights, its k-points have none
        assert rows["bandstructures"].kpoint_weights is None

    def test_reading_all_of_the_k_points_is_not_the_band_structure(self, scf_line):
        """Without the SCF Line handling, the mesh and path are mixed, and the path is not found."""
        from emmet.core.vasp.calculation import _parse_bandstructure_file

        directory, _, rows = scf_line
        vasprun = Vasprun(directory / "vasprun.xml.gz")
        plain = _parse_bandstructure_file(
            "auto", directory / "vasprun.xml.gz", dict(vasprun.incar), True
        )
        assert len(plain.qpoints) == len(vasprun.actual_kpoints)
        assert len(plain.qpoints) > len(rows["bandstructures"].qpoints)
        assert plain.path_convention == BSPathType.unknown

    def test_a_failure_to_read_the_path_is_an_error(self, scf_line, monkeypatch):
        directory, _, _ = scf_line
        (directory / "KPOINTS.gz").unlink()
        parsed, rows = parse(directory)
        assert "bandstructures" not in tables(rows)
        assert any("band structure" in err for err in parsed.errors)
        assert "total-dos" in tables(rows)

    def test_the_calculations_own_kpoints_is_used(self, scf_line):
        """pymatgen looks for a file named KPOINTS; the one discovery chose may be named otherwise."""
        directory, _, rows = scf_line
        # the files of a calculation which has a suffix, as in a multi-calculation directory
        for path in directory.iterdir():
            parts = path.name.split(".")
            if parts[0] in {
                "KPOINTS",
                "INCAR",
                "vasprun",
                "OUTCAR",
                "CONTCAR",
                "POSCAR",
            }:
                stem = ".".join(p for p in parts if p != "gz")
                path.rename(directory / f"{stem}.static.gz")

        parsed, suffixed_rows = parse(directory)
        assert parsed.errors == []
        suffixed = dict(suffixed_rows)["bandstructures"]
        # no file called KPOINTS exists, and the path is still found
        assert (
            not list(directory.glob("KPOINTS.gz"))
            and not (directory / "KPOINTS").exists()
        )
        assert suffixed.path_convention == rows["bandstructures"].path_convention
        assert len(suffixed.qpoints) == len(rows["bandstructures"].qpoints)


class TestVolumetricParsing:
    """Each kind of volumetric file is parsed into the table of its kind."""

    @pytest.fixture
    def static_directory(self, extract):
        return extract("Si_static")

    def rows_of(self, directory, **policy):
        policy.setdefault("volumetric_types", None)
        parsed, rows = parse(directory, policy=ParsePolicy(**policy))
        assert parsed.errors == []
        return parsed, rows

    def test_the_values_are_the_charge_times_the_cell_volume(self, static_directory):
        """n(r) = value / V_cell, and the sum of the values over the grid is NELECT * N_grid."""
        parsed, rows = self.rows_of(static_directory)
        row = dict(rows)["charge-density"]
        vasprun = Vasprun(static_directory / "vasprun.xml.gz")
        nelect = vasprun.parameters["NELECT"]
        total = np.asarray(row.total, dtype=np.float64)
        assert total.size == int(np.prod(row.grid_shape))
        assert total.sum() / total.size == pytest.approx(nelect, rel=1e-4)
        # so the density, in 1/Angstrom^3, integrates to the number of electrons
        volume = abs(np.linalg.det(np.array(row.lattice)))
        density = total / volume
        assert density.sum() * volume / total.size == pytest.approx(nelect, rel=1e-4)

    def test_the_settings_of_the_calculation_are_on_the_row(self, static_directory):
        shutil.copy(static_directory / "CHGCAR.gz", static_directory / "LOCPOT.gz")
        _, rows = self.rows_of(static_directory)
        potential = dict(rows)["local-potential"]
        # these are the effective parameters of the vasprun, and include defaults:
        # LVHAR was not set by the user
        assert potential.lvtot is True and potential.lvhar is False
        assert potential.potential_kind == "total"
        assert potential.spin_mode.value == "collinear"
        assert potential.saxis is None

    def test_each_aeccar_is_a_row_of_its_own(self, static_directory):
        for name in ("AECCAR0", "AECCAR1", "AECCAR2"):
            shutil.copy(static_directory / "CHGCAR.gz", static_directory / f"{name}.gz")
        _, rows = self.rows_of(static_directory)
        by_table = {}
        for table, row in rows:
            by_table.setdefault(table, []).append(row)
        for table, name in (
            ("core-density", "AECCAR0.gz"),
            ("atomic-density", "AECCAR1.gz"),
            ("valence-density", "AECCAR2.gz"),
        ):
            (row,) = by_table[table]
            assert row.file_name == name
        # and a missing one is not a failure of the others
        (static_directory / "AECCAR1.gz").unlink()
        _, rows = self.rows_of(static_directory)
        assert "atomic-density" not in tables(rows)
        assert {"core-density", "valence-density"} <= set(tables(rows))

    def test_every_partial_charge_density_is_a_row(self, static_directory):
        names = [
            "PARCHG.0001.0001.gz",
            "PARCHG.0001.0002.gz",
            "PARCHG.0002.ALLK.gz",
            "PARCHG.ALLB.0002.gz",
            "PARCHG.gz",
        ]
        for name in names:
            shutil.copy(static_directory / "CHGCAR.gz", static_directory / name)
        (source,) = sources(static_directory)
        # discovery accepted every name
        assert len(source.files.extra_parchg) + 1 == len(names)

        _, rows = self.rows_of(static_directory)
        parchg = [row for table, row in rows if table == "partial-charge-density"]
        assert sorted(row.file_name for row in parchg) == sorted(names)
        assert sorted(
            ((row.band_index, row.kpoint_index) for row in parchg),
            key=lambda x: (x[0] is None, x[0] or 0, x[1] is None, x[1] or 0),
        ) == [(1, 1), (1, 2), (2, None), (None, 2), (None, None)]
        # together with the identifier, they identify a row
        assert (
            len({(row.identifier, row.band_index, row.kpoint_index) for row in parchg})
            == 5
        )

    def test_parchg_selection_settings_are_on_the_row(self, static_directory):
        shutil.copy(
            static_directory / "CHGCAR.gz", static_directory / "PARCHG.0003.ALLK.gz"
        )
        (source,) = sources(static_directory)
        policy = ParsePolicy(volumetric_types=("PARCHG",))

        # the vasprun of this calculation did not set the selection
        parsed = parse_calculation(source, ID_1, policy)
        (_, row) = next(parsed.objects())
        assert (row.band_index, row.kpoint_index) == (3, None)
        assert row.iband is None and row.kpuse is None and row.lsepb is None

        # settings which the vasprun does have are given to the rows
        parsed = parse_calculation(source, ID_1, policy)
        parsed._parameters.update({"IBAND": [3], "KPUSE": [1, 2], "LSEPB": True})
        (_, row) = next(parsed.objects())
        assert row.iband == [3] and row.kpuse == [1, 2] and row.lsepb is True

    def test_the_parameters_that_describe_volumetric_files_are_kept(self):
        from emmet.core.vasp.parse import _VOLUMETRIC_PARAMETERS

        assert set(_VOLUMETRIC_PARAMETERS) == {
            "SAXIS",
            "LVTOT",
            "LVHAR",
            "WRT_POTENTIAL",
            "IBAND",
            "EINT",
            "NBMOD",
            "KPUSE",
            "LSEPB",
            "LSEPK",
        }

    def test_an_unreadable_parchg_does_not_affect_the_others(self, static_directory):
        shutil.copy(
            static_directory / "CHGCAR.gz", static_directory / "PARCHG.0001.0001.gz"
        )
        (static_directory / "PARCHG.0001.0002.gz").write_bytes(b"not a PARCHG")
        parsed, rows = parse(
            static_directory, policy=ParsePolicy(volumetric_types=("PARCHG", "CHGCAR"))
        )
        assert len(parsed.errors) == 1 and "PARCHG.0001.0002.gz" in parsed.errors[0]
        parchg = [row for table, row in rows if table == "partial-charge-density"]
        assert [row.file_name for row in parchg] == ["PARCHG.0001.0001.gz"]
        assert "charge-density" in tables(rows)
