"""Test the row models and table registry of the parsed tier."""

import subprocess
import sys
import textwrap
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from emmet.core import ARROW_COMPATIBLE
from emmet.core.io.pymatgen import Chgcar, Elfcar, Locpot, Vasprun
from emmet.core.testing_utils import DataArchive, assert_nested_close
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.vasp.models import VOLUMETRIC_PARSERS
from emmet.core.vasp.parsed import (
    PARSED_TABLES,
    BandStructureRow,
    DosRow,
    ParsedRowHeader,
    ValidationRow,
    VolumetricRow,
    volumetric_table_name,
)

if ARROW_COMPATIBLE:
    import pyarrow as pa
    import pyarrow.parquet as pq

    from emmet.core.arrow import arrowize

COMPLETED_AT = datetime(2020, 3, 11, 1, 50, 16, tzinfo=UTC)


def header(**overrides):
    return {
        "identifier": "mp-1",
        "completed_at": COMPLETED_AT,
        "run_type": RunType.GGA,
        "task_type": TaskType.Static,
        "formula_pretty": "Si",
        "chemsys": "Si",
        **overrides,
    }


@pytest.fixture(scope="module")
def dos(test_dir):
    vasprun = DataArchive.extract_obj(
        test_dir / "vasp/Si_uniform.json.gz",
        "vasprun.xml.gz",
        Vasprun,
        parse_projected_eigen=True,
    )
    return vasprun.complete_dos


@pytest.fixture(scope="module")
def band_structure(test_dir):
    vasprun = DataArchive.extract_obj(
        test_dir / "vasp/r2scan_relax.json.gz",
        "vasprun.xml.gz",
        Vasprun,
        parse_projected_eigen=True,
    )
    return vasprun.get_band_structure()


def test_import_without_pyarrow():
    """The row models are importable without pyarrow."""
    code = textwrap.dedent(
        """
        import sys

        sys.modules["pyarrow"] = None

        from emmet.core.vasp.parsed import PARSED_TABLES, ParsedRowHeader

        assert "validation" in PARSED_TABLES
        assert "year" in ParsedRowHeader.model_fields
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


class TestHeader:
    def test_partition_date_is_derived(self):
        row = ParsedRowHeader(**header())
        assert (row.year, row.month, row.day) == (2020, 3, 11)

        # the date columns cannot disagree with completed_at
        row = ParsedRowHeader(**header(year=1999, month=1, day=1))
        assert (row.year, row.month, row.day) == (2020, 3, 11)

    @pytest.mark.parametrize(
        "completed_at",
        [
            datetime(2020, 3, 11, 1, 50, 16),
            "2020-03-11T01:50:16",
            "2020-03-11T01:50:16+00:00",
            {"$date": "2020-03-11T01:50:16"},
        ],
    )
    def test_completed_at_formats(self, completed_at):
        row = ParsedRowHeader(**header(completed_at=completed_at))
        assert row.completed_at == COMPLETED_AT
        assert row.completed_at.tzinfo is not None

    def test_date_uses_utc_date(self):
        # dates are the date of the (UTC) timestamp, not the local time zone
        late = datetime(2020, 12, 31, 23, 0, tzinfo=UTC)
        row = ParsedRowHeader(**header(completed_at=late))
        assert (row.year, row.month, row.day) == (2020, 12, 31)

        # an aware, non-UTC timestamp keeps its own calendar date
        local = datetime(2020, 12, 31, 23, 0, tzinfo=timezone(timedelta(hours=-8)))
        row = ParsedRowHeader(**header(completed_at=local))
        assert row.completed_at == local
        assert (row.year, row.month, row.day) == (2020, 12, 31)

    @pytest.mark.parametrize("missing", ["completed_at", None])
    def test_completed_at_required(self, missing):
        """A missing time must not silently be replaced with now."""
        config = header()
        if missing:
            config.pop(missing)
        else:
            config["completed_at"] = None
        with pytest.raises(ValidationError, match="completed_at"):
            ParsedRowHeader(**config)

    @pytest.mark.parametrize(
        "field", ["identifier", "run_type", "task_type", "formula_pretty", "chemsys"]
    )
    def test_required_fields(self, field):
        config = header()
        config.pop(field)
        with pytest.raises(ValidationError, match=field):
            ParsedRowHeader(**config)


def test_rows_from_pmg(dos, band_structure, volumetric_files):
    dos_row = DosRow.from_pmg(dos, **header())
    assert isinstance(dos_row, DosRow)
    assert (dos_row.year, dos_row.month, dos_row.day) == (2020, 3, 11)
    assert dos_row.identifier == "mp-1"
    assert dos_row.run_type == RunType.GGA
    assert dos_row.spin_up_densities is not None
    assert dos_row.structure is not None

    bs_row = BandStructureRow.from_pmg(band_structure, **header())
    assert isinstance(bs_row, BandStructureRow)
    assert bs_row.chemsys == "Si"
    assert bs_row.spin_up_bands is not None
    assert bs_row.path_convention is not None

    chgcar = Chgcar.from_file(volumetric_files["collinear"])
    vol_row = VolumetricRow.from_pmg(chgcar, **header(), file_name="CHGCAR.relax1.gz")
    assert isinstance(vol_row, VolumetricRow)
    assert vol_row.file_name == "CHGCAR.relax1.gz"
    assert vol_row.labels is not None and len(vol_row.data) == len(vol_row.labels)

    # file name is required
    with pytest.raises(ValidationError, match="file_name"):
        VolumetricRow.from_pmg(chgcar, **header())

    # so are the header fields
    with pytest.raises(ValidationError, match="chemsys"):
        header_missing = header()
        header_missing.pop("chemsys")
        VolumetricRow.from_pmg(chgcar, **header_missing, file_name="CHGCAR")


def test_validation_row():
    row = ValidationRow(**header(), valid=False, reasons=["bad KPOINTS"])
    assert not row.valid
    assert row.reasons == ["bad KPOINTS"]
    assert row.warnings == []
    assert (row.year, row.month, row.day) == (2020, 3, 11)

    with pytest.raises(ValidationError, match="valid"):
        ValidationRow(**header())


def test_table_registry():
    volumetric = {k.lower() for k in VOLUMETRIC_PARSERS}
    assert volumetric == {
        "chgcar",
        "chg",
        "aeccar0",
        "aeccar1",
        "aeccar2",
        "pot",
        "parchg",
        "locpot",
        "elfcar",
    }
    assert set(PARSED_TABLES) == {"dos", "bandstructure", "validation"} | volumetric

    assert all(name == spec.name for name, spec in PARSED_TABLES.items())
    assert all(spec.zorder_by == ("identifier",) for spec in PARSED_TABLES.values())

    assert PARSED_TABLES["dos"].partition_by == ("run_type",)
    assert PARSED_TABLES["bandstructure"].partition_by == ("run_type", "path_convention")
    assert PARSED_TABLES["validation"].partition_by == ()
    for name in volumetric:
        assert PARSED_TABLES[name].row_model is VolumetricRow
        assert PARSED_TABLES[name].partition_by == ("year", "month", "day", "run_type")

    # every column used to lay out a table is a column of the table
    for spec in PARSED_TABLES.values():
        assert set(spec.partition_by) | set(spec.zorder_by) <= spec.columns


@pytest.mark.parametrize(
    "file_name, table",
    [
        ("CHGCAR", "chgcar"),
        ("CHGCAR.relax1.gz", "chgcar"),
        ("CHG.relax2.gz", "chg"),
        ("PARCHG", "parchg"),
        ("AECCAR1.gz", "aeccar1"),
        ("LOCPOT", "locpot"),
        ("POTCAR", None),
        ("vasprun.xml", None),
    ],
)
def test_volumetric_table_name(file_name, table):
    assert volumetric_table_name(file_name) == table
    assert table is None or table in PARSED_TABLES


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
class TestArrow:
    def test_schemas(self):
        schemas = {
            name: pa.schema(arrowize(spec.row_model))
            for name, spec in PARSED_TABLES.items()
        }

        for name, schema in schemas.items():
            spec = PARSED_TABLES[name]
            assert set(spec.partition_by) | set(spec.zorder_by) <= set(schema.names)

            assert schema.field("identifier").type == pa.string()
            assert schema.field("completed_at").type == pa.timestamp("us", tz="UTC")
            for col in ("year", "month", "day"):
                assert schema.field(col).type == pa.int64()
            for col in ("run_type", "task_type", "formula_pretty", "chemsys"):
                assert schema.field(col).type == pa.string()

        assert schemas["dos"].field("spin_up_densities").type == pa.list_(pa.float32())
        assert schemas["bandstructure"].field("spin_up_bands").type == pa.list_(
            pa.list_(pa.float32())
        )
        assert schemas["bandstructure"].field("path_convention").type == pa.string()
        assert schemas["chgcar"].field("data").type == pa.list_(
            pa.large_list(pa.float32())
        )
        assert schemas["chgcar"].field("file_name").type == pa.string()
        assert schemas["validation"].field("valid").type == pa.bool_()

        # all volumetric tables share a schema
        assert all(
            schemas[name] == schemas["chgcar"]
            for name in PARSED_TABLES
            if name in {k.lower() for k in VOLUMETRIC_PARSERS}
        )

    def test_batch_roundtrip(self, dos, band_structure, volumetric_files):
        """Mixed batches of rows share a schema, and survive a trip through arrow."""
        dos_row = DosRow.from_pmg(dos, **header())
        bs_row = BandStructureRow.from_pmg(
            band_structure, **header(run_type=RunType.r2SCAN)
        )

        # a nonmagnetic dos has no spin-down densities, and no projections
        dos_row_nospin = DosRow(
            **header(identifier="mp-2"),
            spin_up_densities=[0.0, 1.0],
            energies=[-1.0, 1.0],
            efermi=0.0,
        )

        entries = [
            (Chgcar, "collinear", "CHGCAR"),
            (Chgcar, "unpolarized", "AECCAR0.relax1.gz"),
            (Chgcar, "noncollinear", "CHG"),
            (Locpot, "collinear_no_aug", "LOCPOT"),
            (Elfcar, "unpolarized", "ELFCAR"),
        ]
        pmg_objs = [cls.from_file(volumetric_files[key]) for cls, key, _ in entries]
        vol_rows = [
            VolumetricRow.from_pmg(
                obj,
                **header(identifier=f"mp-{i}"),
                file_name=file_name,
            )
            for i, (obj, (_, _, file_name)) in enumerate(zip(pmg_objs, entries))
        ]

        for rows, table_name in (
            ([dos_row, dos_row_nospin], "dos"),
            ([bs_row], "bandstructure"),
            (vol_rows, "chgcar"),
        ):
            spec = PARSED_TABLES[table_name]
            schema = pa.schema(arrowize(spec.row_model))
            table = pa.Table.from_pylist(
                [row.model_dump(context={"format": "arrow"}) for row in rows],
                schema=schema,
            )
            assert table.schema == schema
            assert table.num_rows == len(rows)

            for row, table_row in zip(rows, table.to_pylist(maps_as_pydicts="strict")):
                restored = type(row)(**table_row)
                assert restored.identifier == row.identifier
                assert restored.completed_at == COMPLETED_AT
                assert (restored.year, restored.month, restored.day) == (2020, 3, 11)
                assert_nested_close(restored, row)

    def test_partitioned_write(self, volumetric_files, tmp_path):
        """Rows are laid out by their partition columns, including awkward run types."""
        chgcar = Chgcar.from_file(volumetric_files["collinear"])
        rows = [
            VolumetricRow.from_pmg(
                chgcar,
                **header(
                    identifier=f"mp-{i}",
                    run_type=run_type,
                    completed_at=completed_at,
                ),
                file_name="CHGCAR",
            )
            for i, (run_type, completed_at) in enumerate(
                [
                    (RunType.GGA, COMPLETED_AT),
                    (RunType.GGA_U, COMPLETED_AT),
                    (RunType.r2SCAN, datetime(2021, 1, 2, tzinfo=UTC)),
                ]
            )
        ]

        spec = PARSED_TABLES["chgcar"]
        table = pa.Table.from_pylist(
            [row.model_dump(context={"format": "arrow"}) for row in rows],
            schema=pa.schema(arrowize(spec.row_model)),
        )
        pq.write_to_dataset(
            table,
            tmp_path / "chgcar",
            partition_cols=list(spec.partition_by),
        )

        parts = {
            p.relative_to(tmp_path / "chgcar").parent.as_posix()
            for p in (tmp_path / "chgcar").rglob("*.parquet")
        }
        assert len(parts) == 3
        assert any("year=2021/month=1/day=2/" in p for p in parts)

        # no data is lost reading the dataset back, including the awkward "GGA+U"
        # partition value, which is escaped in the directory name
        restored = pq.read_table(tmp_path / "chgcar", partitioning="hive")
        assert restored.num_rows == 3
        assert sorted(restored["identifier"].to_pylist()) == ["mp-0", "mp-1", "mp-2"]
        assert {str(r) for r in restored["run_type"].to_pylist()} == {
            str(RunType.GGA),
            str(RunType.GGA_U),
            str(RunType.r2SCAN),
        }
