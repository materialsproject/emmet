"""Test the parsing of a calculation into the rows of the parsed tier."""

import gc
import os
import shutil
import sys
import time
import weakref
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from emmet.core import ARROW_COMPATIBLE
from emmet.core.io.pymatgen import Vasprun
from emmet.core.tasks import CoreTaskDoc
from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive, assert_nested_close
from emmet.core.types.enums import TaskState
from emmet.core.vasp.calc_types.enums import TaskType
from emmet.core.vasp.calculation import Calculation
from emmet.core.vasp.models import VOLUMETRIC_PARSERS
from emmet.core.vasp.parse import (
    MP_PRODUCTION,
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
    VolumetricRow,
    band_structure_from_rows,
    dos_from_rows,
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


def parse(directory, identifier=ID_1, policy=MP_PRODUCTION, **kwargs):
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
        wanted = task_type.value in {"Static", "NSCF Uniform", "NSCF Line"}
        assert MP_PRODUCTION.wants_dos(task_type) is wanted
        assert MP_PRODUCTION.wants_bandstructure(task_type) is wanted

    def test_mp_production(self):
        assert MP_PRODUCTION == ParsePolicy()
        assert MP_PRODUCTION.volumetric_types is None
        assert not MP_PRODUCTION.include_failed
        assert MP_PRODUCTION.require_known_task_type
        assert MP_PRODUCTION.dos_projections and MP_PRODUCTION.bandstructure_projections
        assert all(MP_PRODUCTION.wants_volumetric(t) for t in VOLUMETRIC_PARSERS)

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
        assert not MP_PRODUCTION.wants_dos(None) and everything.wants_dos(None)

    def test_volumetric_types(self):
        policy = ParsePolicy(volumetric_types=("chgcar", "LOCPOT"))
        assert policy.volumetric_types == ("CHGCAR", "LOCPOT")
        assert policy.wants_volumetric("CHGCAR") and policy.wants_volumetric("LOCPOT")
        assert not policy.wants_volumetric("AECCAR0")
        assert not ParsePolicy(volumetric_types=()).wants_volumetric("CHGCAR")

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
        assert by_table["total-dos"].projected_densities is None
        assert by_table["bandstructures"].projections is None
        assert by_table["projected-bandstructures"].path_convention == (
            by_table["bandstructures"].path_convention
        )

        # the objects are those of the vasprun
        vasprun = Vasprun(directory / "vasprun.xml.gz", parse_projected_eigen=True)
        dos = dos_from_rows(by_table["total-dos"], by_table["projected-dos"]).to_pmg()
        assert dos.structure == vasprun.complete_dos.structure
        for spin, densities in vasprun.complete_dos.densities.items():
            assert np.allclose(dos.densities[spin], densities)
        assert set(dos.pdos) == set(vasprun.complete_dos.pdos)

        band_structure = band_structure_from_rows(
            by_table["bandstructures"], by_table["projected-bandstructures"]
        ).to_pmg()
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
        """A structure optimization is not given electronic structure by MP's policy."""
        directory = extract("Si_static")
        parsed, rows = parse(directory)

        assert parsed.task.task_type == TaskType.Structure_Optimization
        assert tables(rows) == ["chgcar"]
        row = rows[0][1]
        assert isinstance(row, VolumetricRow)
        assert row.file_name == "CHGCAR.gz"
        assert [lab.value for lab in row.labels] in (["total"], ["total", "diff"])
        assert row.run_type == parsed.task.run_type
        # the structure in a CHGCAR is the one it was written for, not necessarily the final one
        assert row.structure.composition == parsed.task.structure.composition

        # the volumetric data is that of the file
        from emmet.core.io.pymatgen import Chgcar

        pmg_chgcar = Chgcar.from_file(str(directory / "CHGCAR.gz"))
        assert np.allclose(
            row.to_pmg(pmg_cls=Chgcar).data["total"], pmg_chgcar.data["total"]
        )

    def test_policy_selects_objects(self, extract):
        directory = extract("Si_static")

        def objects(**policy):
            _, rows = parse(directory, policy=ParsePolicy(**policy))
            return tables(rows)

        everything = {"dos_task_types": None, "bandstructure_task_types": None}
        assert "chgcar" in objects(**everything)
        assert objects(**everything)[:2] == ["total-dos", "projected-dos"]
        assert "bandstructures" in objects(**everything)

        assert "chgcar" not in objects(volumetric_types=())
        assert "chgcar" not in objects(volumetric_types=("LOCPOT",))
        assert objects(volumetric_types=("CHGCAR",)) == ["chgcar"]

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
            "chgcar",
        ]

    def test_legacy_directory(self, extract):
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

        # relaxations have no electronic structure in MP's policy, but can
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
        assert tables(rows) == ["chgcar"]


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
        assert sorted(tables(rows)) == ["aeccar0", "locpot"]
        assert len(parsed.errors) == 1 and "CHGCAR.gz" in parsed.errors[0]

        manifest = parsed.manifest_row()
        assert sorted(manifest.tables) == ["aeccar0", "locpot"]
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
        "chgcar",
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

    def test_legacy_directory_needs_a_suffix(self, extract):
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
