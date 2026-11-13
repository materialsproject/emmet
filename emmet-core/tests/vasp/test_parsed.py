"""Test the row models and table registry of the parsed tier."""

import subprocess
import sys
import textwrap
from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pytest
from pydantic import TypeAdapter, ValidationError

from emmet.core import ARROW_COMPATIBLE
from emmet.core.io.pymatgen import Chgcar, CompleteDos, Dos, Vasprun
from emmet.core.testing_utils import DataArchive, assert_nested_close
from emmet.core.types.typing import IdentifierType
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.vasp.models import VOLUMETRIC_PARSERS
from emmet.core.band_theory import BSPathType
from emmet.core.tasks import CoreTaskDoc
from emmet.core.vasp.parsed import (
    PARSED_TABLES,
    BandStructureProjectionsRow,
    BandStructureRow,
    DosProjectionsRow,
    DosRow,
    ManifestRow,
    ParseOutcome,
    ParsedRowHeader,
    TrajectoryRow,
    ValidationRow,
    VOLUMETRIC_FILE_TABLES,
    ChargeDensityRow,
    SpinMode,
    split_band_structure_row,
    split_dos_row,
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
    assert dos_row.density is not None and dos_row.density_up is None
    assert dos_row.spin_mode == SpinMode.UNPOLARIZED
    assert dos_row.structure == dos.structure
    # the projections are made with the row, but are not part of what is stored
    assert dos_row._projections is not None
    assert not {"projections", "_projections"} & set(dos_row.model_dump())

    bs_row = BandStructureRow.from_pmg(band_structure, **header())
    assert isinstance(bs_row, BandStructureRow)
    assert bs_row.chemsys == "Si"
    # the band structure of this calculation is spin-polarized
    assert bs_row.spin_mode == SpinMode.COLLINEAR
    assert bs_row.bands is None and bs_row.bands_up is not None
    assert bs_row.path_convention is not None
    assert bs_row._projections is not None
    assert not {"projections", "_projections"} & set(bs_row.model_dump())

    chgcar = Chgcar.from_file(volumetric_files["collinear"])
    vol_row = ChargeDensityRow.from_pmg(
        chgcar, **header(), file_name="CHGCAR.relax1.gz"
    )
    assert isinstance(vol_row, ChargeDensityRow)
    assert vol_row.file_name == "CHGCAR.relax1.gz"
    assert vol_row.spin_mode == SpinMode.COLLINEAR
    assert vol_row.total is not None and vol_row.magnetization is not None
    assert vol_row.magnetization_1 is None

    # file name is required
    with pytest.raises(ValidationError, match="file_name"):
        ChargeDensityRow.from_pmg(chgcar, **header())

    # so are the header fields
    with pytest.raises(ValidationError, match="chemsys"):
        header_missing = header()
        header_missing.pop("chemsys")
        ChargeDensityRow.from_pmg(chgcar, **header_missing, file_name="CHGCAR")


def test_validation_row():
    row = ValidationRow(**header(), valid=False, reasons=["bad KPOINTS"])
    assert not row.valid
    assert row.reasons == ["bad KPOINTS"]
    assert row.warnings == []
    assert (row.year, row.month, row.day) == (2020, 3, 11)

    with pytest.raises(ValidationError, match="valid"):
        ValidationRow(**header())


def test_table_registry():
    volumetric = set(VOLUMETRIC_FILE_TABLES.values())
    # every type of volumetric file the parser reads has a table
    assert set(VOLUMETRIC_FILE_TABLES) == set(VOLUMETRIC_PARSERS)
    assert volumetric == {
        "charge-density",
        "partial-charge-density",
        "core-density",
        "atomic-density",
        "valence-density",
        "local-potential",
        "electron-localization",
        "charge-density-chg",
        "local-potential-pot",
    }
    # the names of the DOS and band structure tables are those in production
    assert (
        set(PARSED_TABLES)
        == {
            "total-dos",
            "projected-dos",
            "bandstructures",
            "projected-bandstructures",
            "validation",
            "manifest",
            "tasks",
            "trajectories",
        }
        | volumetric
    )

    assert all(name == spec.name for name, spec in PARSED_TABLES.items())
    assert PARSED_TABLES["tasks"].row_model is CoreTaskDoc
    assert PARSED_TABLES["tasks"].partition_by == ()
    assert PARSED_TABLES["tasks"].zorder_by == ("task_id",)
    assert PARSED_TABLES["trajectories"].row_model is TrajectoryRow
    assert PARSED_TABLES["trajectories"].partition_by == ("run_type",)
    assert all(
        spec.zorder_by == ("identifier",)
        for name, spec in PARSED_TABLES.items()
        if name != "tasks"
    )

    assert PARSED_TABLES["total-dos"].row_model is DosRow
    assert PARSED_TABLES["projected-dos"].row_model is DosProjectionsRow
    assert PARSED_TABLES["bandstructures"].row_model is BandStructureRow
    assert (
        PARSED_TABLES["projected-bandstructures"].row_model
        is BandStructureProjectionsRow
    )
    assert PARSED_TABLES["total-dos"].partition_by == ("run_type",)
    assert PARSED_TABLES["projected-dos"].partition_by == ("run_type",)
    # the order is that of the tables in production: run type, then path convention
    for name in ("bandstructures", "projected-bandstructures"):
        assert PARSED_TABLES[name].partition_by == ("run_type", "path_convention")
    assert PARSED_TABLES["validation"].partition_by == ()
    assert PARSED_TABLES["manifest"].partition_by == ()
    for name in volumetric:
        assert PARSED_TABLES[name].partition_by == ("year", "month", "day", "run_type")
    # each kind of data has its own model, as the blocks of its files mean different things
    assert PARSED_TABLES["charge-density"].row_model is ChargeDensityRow
    assert PARSED_TABLES["charge-density-chg"].row_model is ChargeDensityRow
    assert PARSED_TABLES["local-potential-pot"].row_model is (
        PARSED_TABLES["local-potential"].row_model
    )
    assert PARSED_TABLES["core-density"].row_model is (
        PARSED_TABLES["valence-density"].row_model
    )

    # every column used to lay out a table is a column of the table
    for spec in PARSED_TABLES.values():
        assert set(spec.partition_by) | set(spec.zorder_by) <= spec.columns


@pytest.mark.parametrize(
    "file_name, table",
    [
        ("CHGCAR", "charge-density"),
        ("CHGCAR.relax1.gz", "charge-density"),
        ("CHG.relax2.gz", "charge-density-chg"),
        ("PARCHG", "partial-charge-density"),
        ("PARCHG.0001.ALLK", "partial-charge-density"),
        ("AECCAR0", "core-density"),
        ("AECCAR1.gz", "atomic-density"),
        ("AECCAR2", "valence-density"),
        ("LOCPOT", "local-potential"),
        ("POT", "local-potential-pot"),
        ("ELFCAR", "electron-localization"),
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
            if name != "tasks":
                assert schema.field("identifier").type == pa.string()
            if name != "trajectories":
                assert schema.field("completed_at").type == pa.timestamp("us", tz="UTC")

            if name in ("manifest", "tasks", "trajectories"):
                # these do not have the header of the tables of large objects
                continue
            for col in ("year", "month", "day"):
                assert schema.field(col).type == pa.int64()
            for col in ("run_type", "task_type", "formula_pretty", "chemsys"):
                assert schema.field(col).type == pa.string()

        # projections are not columns of the tables of the DOS and band structure
        assert "projected_densities" not in schemas["total-dos"].names
        assert "projections" not in schemas["bandstructures"].names
        # nor is a pymatgen structure: the structure of every table is its lattice and sites
        for name in ("total-dos", "bandstructures"):
            assert {"lattice", "species", "frac_coords"} <= set(schemas[name].names)
            assert "structure" not in schemas[name].names

        assert schemas["total-dos"].field("energies").type == pa.list_(pa.float32())
        assert schemas["total-dos"].field("density").type == pa.list_(pa.float32())
        assert schemas["total-dos"].field("integrated_up").type == pa.list_(
            pa.float32()
        )
        assert schemas["projected-dos"].field("density").type == pa.large_list(
            pa.float32()
        )
        assert schemas["projected-dos"].field("orbitals").type == pa.list_(pa.string())
        assert schemas["projected-dos"].field("shape").type == pa.list_(pa.int64())
        assert schemas["bandstructures"].field("bands").type == pa.large_list(
            pa.float32()
        )
        assert schemas["bandstructures"].field("kpoint_labels").type == pa.list_(
            pa.string()
        )
        assert schemas["bandstructures"].field("path_convention").type == pa.string()
        assert schemas["projected-bandstructures"].field("weights").type == (
            pa.large_list(pa.float32())
        )
        # path convention is a column of both band structure tables, as they are
        # partitioned by it
        assert schemas["projected-bandstructures"].field("path_convention").type == (
            pa.string()
        )
        assert schemas["charge-density"].field("total").type == pa.large_list(
            pa.float32()
        )
        assert schemas["charge-density"].field("file_name").type == pa.string()
        # the structure of a volumetric file is its lattice and sites, not a pymatgen dict
        for name in set(VOLUMETRIC_FILE_TABLES.values()):
            fields = set(schemas[name].names)
            assert {"lattice", "species", "frac_coords", "grid_shape"} <= fields
            assert not {"structure", "data_aug", "data", "labels"} & fields
        assert schemas["validation"].field("valid").type == pa.bool_()
        assert schemas["manifest"].field("tables").type == pa.list_(pa.string())
        assert schemas["manifest"].field("outcome").type == pa.string()

    def test_batch_roundtrip(self, dos, band_structure, volumetric_files):
        """Mixed batches of rows share a schema, and survive a trip through arrow."""
        dos_row, dos_projections = split_dos_row(DosRow.from_pmg(dos, **header()))
        bs_row, bs_projections = split_band_structure_row(
            BandStructureRow.from_pmg(band_structure, **header(run_type=RunType.r2SCAN))
        )
        assert dos_projections is not None and bs_projections is not None

        # a DOS with no integrated DOS and settings, and no projections
        dos_row_nospin = DosRow(
            **header(identifier="mp-2"),
            spin_mode=SpinMode.UNPOLARIZED,
            lattice=np.eye(3).tolist(),
            species=["Si"],
            frac_coords=[[0.0, 0.0, 0.0]],
            density=[0.0, 1.0],
            energies=[-1.0, 1.0],
            efermi=0.0,
        )

        chgcars = [
            Chgcar.from_file(volumetric_files[key])
            for key in ("collinear", "unpolarized", "noncollinear")
        ]
        vol_rows = [
            ChargeDensityRow.from_pmg(
                obj,
                **header(identifier=f"mp-{i}"),
                file_name=file_name,
            )
            for i, (obj, file_name) in enumerate(
                zip(chgcars, ("CHGCAR", "CHGCAR.relax1.gz", "CHGCAR.relax2.gz"))
            )
        ]
        assert [row.spin_mode for row in vol_rows] == [
            SpinMode.COLLINEAR,
            SpinMode.UNPOLARIZED,
            SpinMode.NONCOLLINEAR,
        ]

        for rows, table_name in (
            ([dos_row, dos_row_nospin], "total-dos"),
            ([dos_projections], "projected-dos"),
            ([bs_row], "bandstructures"),
            ([bs_projections], "projected-bandstructures"),
            (vol_rows, "charge-density"),
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

    def test_projections_roundtrip(self, dos, band_structure):
        """The DOS and band structure are rebuilt from their tables, projections included."""

        def through_arrow(row, table_name):
            spec = PARSED_TABLES[table_name]
            table = pa.Table.from_pylist(
                [row.model_dump(context={"format": "arrow"})],
                schema=pa.schema(arrowize(spec.row_model)),
            )
            return type(row)(**table.to_pylist(maps_as_pydicts="strict")[0])

        dos_row, dos_proj = split_dos_row(DosRow.from_pmg(dos, **header()))
        rebuilt = through_arrow(dos_row, "total-dos").to_pmg(
            through_arrow(dos_proj, "projected-dos")
        )
        assert rebuilt.pdos and rebuilt.structure == dos.structure
        assert np.allclose(rebuilt.energies, dos.energies, rtol=1e-6)
        for spin, densities in dos.densities.items():
            assert np.allclose(rebuilt.densities[spin], densities, rtol=1e-6, atol=1e-7)
        assert set(rebuilt.pdos) == set(dos.pdos)
        for site, orbitals in dos.pdos.items():
            for orbital, spins in orbitals.items():
                for spin, densities in spins.items():
                    assert np.allclose(
                        rebuilt.pdos[site][orbital][spin],
                        densities,
                        rtol=1e-6,
                        atol=1e-7,
                    )
        # without the projections table it is a total DOS
        assert type(through_arrow(dos_row, "total-dos").to_pmg()) is Dos
        assert isinstance(rebuilt, CompleteDos)

        bs_row, bs_proj = split_band_structure_row(
            BandStructureRow.from_pmg(band_structure, **header())
        )
        rebuilt_bs = through_arrow(bs_row, "bandstructures").to_pmg(
            through_arrow(bs_proj, "projected-bandstructures")
        )
        assert rebuilt_bs.projections and set(rebuilt_bs.projections) == set(
            band_structure.projections
        )
        for spin, proj in band_structure.projections.items():
            assert np.allclose(rebuilt_bs.projections[spin], proj, rtol=1e-6, atol=1e-7)
        for spin, bands in band_structure.bands.items():
            assert np.allclose(rebuilt_bs.bands[spin], bands, rtol=1e-6, atol=1e-6)
        assert not through_arrow(bs_row, "bandstructures").to_pmg().projections

    def test_partitioned_write(self, volumetric_files, tmp_path):
        """Rows are laid out by their partition columns, including awkward run types."""
        chgcar = Chgcar.from_file(volumetric_files["collinear"])
        rows = [
            ChargeDensityRow.from_pmg(
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

        spec = PARSED_TABLES["charge-density"]
        table = pa.Table.from_pylist(
            [row.model_dump(context={"format": "arrow"}) for row in rows],
            schema=pa.schema(arrowize(spec.row_model)),
        )
        pq.write_to_dataset(
            table,
            tmp_path / "charge-density",
            partition_cols=list(spec.partition_by),
        )

        parts = {
            p.relative_to(tmp_path / "charge-density").parent.as_posix()
            for p in (tmp_path / "charge-density").rglob("*.parquet")
        }
        assert len(parts) == 3
        assert any("year=2021/month=1/day=2/" in p for p in parts)

        # no data is lost reading the dataset back, including the awkward "GGA+U"
        # partition value, which is escaped in the directory name
        restored = pq.read_table(tmp_path / "charge-density", partitioning="hive")
        assert restored.num_rows == 3
        # identifiers are normalized to the padded AlphaID form by the row header
        expected_ids = [
            TypeAdapter(IdentifierType).validate_python(f"mp-{i}") for i in range(3)
        ]
        assert sorted(restored["identifier"].to_pylist()) == sorted(expected_ids)
        assert {str(r) for r in restored["run_type"].to_pylist()} == {
            str(RunType.GGA),
            str(RunType.GGA_U),
            str(RunType.r2SCAN),
        }


class TestProjections:
    def test_split_dos(self, dos):
        row = DosRow.from_pmg(dos, **header())
        projections_row = row._projections
        total, projections = split_dos_row(row)

        assert total is row and projections is projections_row
        # the row no longer has them
        assert total.take_projections() is None
        assert isinstance(projections, DosProjectionsRow)
        # the header is the row's
        assert projections.identifier == total.identifier
        assert projections.completed_at == total.completed_at
        assert (projections.year, projections.month, projections.day) == (2020, 3, 11)
        assert projections.run_type == RunType.GGA
        assert projections.chemsys == "Si"
        n_sites = len(dos.structure)
        assert projections.shape == [
            n_sites,
            len(projections.orbitals),
            len(dos.energies),
        ]
        assert len(projections.density) == np.prod(projections.shape)

    def test_split_band_structure(self, band_structure):
        row = BandStructureRow.from_pmg(band_structure, **header())
        projections_row = row._projections
        bs, projections = split_band_structure_row(row)

        assert bs is row and projections is projections_row
        assert bs.take_projections() is None
        assert isinstance(projections, BandStructureProjectionsRow)
        assert projections.identifier == bs.identifier
        assert projections.run_type == bs.run_type == RunType.GGA
        # the path convention partitions both tables
        assert projections.path_convention == bs.path_convention
        assert isinstance(projections.path_convention, BSPathType)
        # the first two axes are those of the bands
        assert projections.shape[:2] == bs.shape
        assert projections.shape[3] == len(bs.species)

    def test_no_projections(self, dos):
        row = DosRow(
            **header(),
            spin_mode=SpinMode.UNPOLARIZED,
            lattice=np.eye(3).tolist(),
            species=["Si"],
            frac_coords=[[0.0, 0.0, 0.0]],
            density=[1.0],
            energies=[0.0],
            efermi=0.0,
        )
        total, projections = split_dos_row(row)
        assert projections is None and total is row

        row = BandStructureRow(
            **header(),
            spin_mode=SpinMode.UNPOLARIZED,
            lattice=np.eye(3).tolist(),
            species=["Si"],
            frac_coords=[[0.0, 0.0, 0.0]],
            path_convention=BSPathType.uniform,
            qpoints=[(0.0, 0.0, 0.0)],
            reciprocal_lattice=np.eye(3).tolist(),
            efermi=0.0,
            shape=[1, 1],
            bands=[0.0],
        )
        bs, projections = split_band_structure_row(row)
        assert projections is None and bs is row

    def test_rebuild_requires_matching_identifiers(self, dos, band_structure):
        dos_row, dos_proj = split_dos_row(DosRow.from_pmg(dos, **header()))
        _, other_proj = split_dos_row(DosRow.from_pmg(dos, **header(identifier="mp-2")))
        with pytest.raises(ValueError, match="do not belong"):
            dos_row.to_pmg(other_proj)
        assert isinstance(dos_row.to_pmg(dos_proj), CompleteDos)

        bs_row, bs_proj = split_band_structure_row(
            BandStructureRow.from_pmg(band_structure, **header())
        )
        _, other_bs_proj = split_band_structure_row(
            BandStructureRow.from_pmg(band_structure, **header(identifier="mp-2"))
        )
        with pytest.raises(ValueError, match="do not belong"):
            bs_row.to_pmg(other_bs_proj)
        assert bs_row.to_pmg(bs_proj).projections


class TestManifest:
    def test_row(self):
        row = ManifestRow(
            identifier="aaaaaaab",
            dir_name="host:/some/launcher",
            calc_suffix="relax1",
            completed_at=COMPLETED_AT,
            outcome=ParseOutcome.PARSED,
            run_type=RunType.GGA,
            task_type=TaskType.Static,
            tables=["charge-density"],
        )
        assert row.identifier == "aaaaaaab"
        assert row.outcome == ParseOutcome.PARSED
        assert row.errors == []
        assert row.parsed_at.tzinfo is not None

    def test_unreadable_calculation(self):
        """A calculation that could not be read has little to say about itself."""
        row = ManifestRow(
            identifier="aaaaaaab",
            dir_name="host:/some/launcher",
            calc_suffix="standard",
            outcome="error",
            errors=["Could not parse the calculation: it was empty"],
        )
        assert row.outcome == ParseOutcome.ERROR
        assert row.completed_at is None and row.run_type is None

    def test_outcomes(self):
        assert {o.value for o in ParseOutcome} == {
            "parsed",
            "skipped_failed",
            "skipped_unrecognized",
            "error",
        }

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_arrow(self):
        schema = pa.schema(arrowize(ManifestRow))
        rows = [
            ManifestRow(
                identifier="aaaaaaab",
                dir_name="host:/a",
                calc_suffix="standard",
                completed_at=COMPLETED_AT,
                outcome="parsed",
                run_type=RunType.GGA,
                task_type=TaskType.Static,
                tables=["charge-density", "local-potential"],
            ),
            ManifestRow(
                identifier="aaaaaaac",
                dir_name="host:/b",
                calc_suffix="relax2",
                outcome="error",
                errors=["bad"],
            ),
        ]
        table = pa.Table.from_pylist(
            [r.model_dump(context={"format": "arrow"}) for r in rows], schema=schema
        )
        restored = [ManifestRow(**r) for r in table.to_pylist()]
        assert [r.outcome for r in restored] == [
            ParseOutcome.PARSED,
            ParseOutcome.ERROR,
        ]
        assert restored[0].tables == ["charge-density", "local-potential"]
        assert restored[1].completed_at is None


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_tasks_table(test_dir):
    from emmet.core.vasp.parse import DirectorySource, parse_calculation

    with DataArchive.extract(test_dir / "vasp" / "Si_uniform.json.gz") as d:
        parsed = parse_calculation(DirectorySource.from_directory(d)[0], "aaaaaaab")
    schema = pa.schema(arrowize(CoreTaskDoc))
    assert schema.field("calc_suffix").type == pa.string()
    assert schema.field("task_id").type == pa.string()

    table = pa.Table.from_pylist(
        [parsed.task.model_dump(context={"format": "arrow"})], schema=schema
    )
    restored = CoreTaskDoc(**table.to_pylist(maps_as_pydicts="strict")[0])
    assert restored.task_id == "aaaaaaab"
    assert restored.calc_suffix == "standard"
    assert restored.completed_at == parsed.task.completed_at


def test_importing_the_tables_does_not_warn():
    """The models of the tables do not raise warnings when they are defined.

    This runs in a new interpreter, as pydantic warns when a class is defined.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error::UserWarning:pydantic",
            "-c",
            "import emmet.core.vasp.parsed",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
