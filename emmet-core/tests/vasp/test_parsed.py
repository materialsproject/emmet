"""Test the row models and table registry of the parsed tier."""

import subprocess
import sys
import textwrap
from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pytest
from pydantic import TypeAdapter, ValidationError

from emmet.core import ARROW_COMPATIBLE
from emmet.core.io.pymatgen import Chgcar, Dos, Vasprun
from emmet.core.testing_utils import DataArchive, assert_nested_close
from emmet.core.trajectory import RelaxTrajectory
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
    band_structure_from_rows,
    dos_from_rows,
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
    assert dos_row.spin_up_densities is not None
    assert dos_row.structure is not None
    # the projections are held by the row, but are not part of what is stored
    assert dos_row.projected_densities is not None
    assert "projected_densities" not in dos_row.model_dump()

    bs_row = BandStructureRow.from_pmg(band_structure, **header())
    assert isinstance(bs_row, BandStructureRow)
    assert bs_row.chemsys == "Si"
    assert bs_row.spin_up_bands is not None
    assert bs_row.path_convention is not None
    assert bs_row.projections is not None
    assert "projections" not in bs_row.model_dump()

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

        assert schemas["total-dos"].field("spin_up_densities").type == pa.list_(
            pa.float32()
        )
        assert schemas["projected-dos"].field("spin_up_densities").type == pa.list_(
            pa.list_(pa.float32())
        )
        assert schemas["projected-dos"].field("site_index").type == pa.list_(pa.int64())
        assert schemas["bandstructures"].field("spin_up_bands").type == pa.list_(
            pa.list_(pa.float32())
        )
        assert schemas["bandstructures"].field("path_convention").type == pa.string()
        assert schemas["projected-bandstructures"].field("spin_up").type == (
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

        # a nonmagnetic dos has no spin-down densities, and no projections
        dos_row_nospin = DosRow(
            **header(identifier="mp-2"),
            spin_up_densities=[0.0, 1.0],
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
        rebuilt = dos_from_rows(
            through_arrow(dos_row, "total-dos"),
            through_arrow(dos_proj, "projected-dos"),
        ).to_pmg()
        assert rebuilt.pdos and rebuilt.structure == dos.structure
        assert np.allclose(rebuilt.energies, dos.energies)
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
        assert type(dos_from_rows(through_arrow(dos_row, "total-dos")).to_pmg()) is Dos

        bs_row, bs_proj = split_band_structure_row(
            BandStructureRow.from_pmg(band_structure, **header())
        )
        rebuilt_bs = band_structure_from_rows(
            through_arrow(bs_row, "bandstructures"),
            through_arrow(bs_proj, "projected-bandstructures"),
        ).to_pmg()
        assert rebuilt_bs.projections and set(rebuilt_bs.projections) == set(
            band_structure.projections
        )
        for spin, proj in band_structure.projections.items():
            assert np.allclose(rebuilt_bs.projections[spin], proj, rtol=1e-6, atol=1e-7)
        for spin, bands in band_structure.bands.items():
            assert np.allclose(rebuilt_bs.bands[spin], bands, rtol=1e-6, atol=1e-6)
        assert not band_structure_from_rows(
            through_arrow(bs_row, "bandstructures")
        ).projections

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
        projections_obj = row.projected_densities
        total, projections = split_dos_row(row)

        assert total is row
        assert total.projected_densities is None
        assert isinstance(projections, DosProjectionsRow)
        # the header is copied, and the data is shared and not copied
        assert projections.identifier == total.identifier
        assert projections.completed_at == total.completed_at
        assert (projections.year, projections.month, projections.day) == (2020, 3, 11)
        assert projections.run_type == RunType.GGA
        assert projections.chemsys == "Si"
        assert projections.spin_up_densities is projections_obj.spin_up_densities
        assert len(projections.orbital) == len(projections.site_index) > 0

    def test_split_band_structure(self, band_structure):
        row = BandStructureRow.from_pmg(band_structure, **header())
        projections_obj = row.projections
        bs, projections = split_band_structure_row(row)

        assert bs is row and bs.projections is None
        assert isinstance(projections, BandStructureProjectionsRow)
        assert projections.identifier == bs.identifier
        assert projections.run_type == bs.run_type == RunType.GGA
        # the path convention partitions both tables
        assert projections.path_convention == bs.path_convention
        assert isinstance(projections.path_convention, BSPathType)
        assert projections.spin_up is projections_obj.spin_up
        assert projections.rank == projections_obj.rank

    def test_no_projections(self, dos):
        row = DosRow(**header(), spin_up_densities=[1.0], energies=[0.0], efermi=0.0)
        total, projections = split_dos_row(row)
        assert projections is None and total is row

        row = BandStructureRow(
            **header(),
            qpoints=[(0.0, 0.0, 0.0)],
            reciprocal_lattice=np.eye(3).tolist(),
            efermi=0.0,
        )
        bs, projections = split_band_structure_row(row)
        assert projections is None and bs is row

    def test_rebuild_requires_matching_identifiers(self, dos, band_structure):
        dos_row, dos_proj = split_dos_row(DosRow.from_pmg(dos, **header()))
        other_dos, other_proj = split_dos_row(
            DosRow.from_pmg(dos, **header(identifier="mp-2"))
        )
        with pytest.raises(ValueError, match="do not belong"):
            dos_from_rows(dos_row, other_proj)
        assert dos_from_rows(dos_row, dos_proj).projected_densities is not None

        bs_row, bs_proj = split_band_structure_row(
            BandStructureRow.from_pmg(band_structure, **header())
        )
        _, other_bs_proj = split_band_structure_row(
            BandStructureRow.from_pmg(band_structure, **header(identifier="mp-2"))
        )
        with pytest.raises(ValueError, match="do not belong"):
            band_structure_from_rows(bs_row, other_bs_proj)
        assert band_structure_from_rows(bs_row, bs_proj).projections is not None


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


class TestTrajectoryRow:
    @pytest.fixture(scope="class")
    def trajectory(self, test_dir):
        from emmet.core.vasp.parse import DirectorySource, parse_calculation

        with DataArchive.extract(
            test_dir / "vasp" / "Si_old_double_relax.json.gz"
        ) as d:
            source = DirectorySource.from_directory(d)[0]
            parsed = parse_calculation(source, "aaaaaaab")
        return parsed.trajectory

    def test_from_trajectory(self, trajectory):
        row = TrajectoryRow.from_trajectory(trajectory)
        assert row.identifier == "aaaaaaab"
        assert row.run_type == trajectory.run_type
        assert row.has_full_output == trajectory.has_full_output
        convergence = trajectory.convergence_data
        for name in ("energy", "e_fr_energy", "e_wo_entrp", "forces"):
            assert getattr(row, f"{name}_convergence") == convergence.get(name)
        assert row.energy == trajectory.energy
        assert row.num_ionic_steps == trajectory.num_ionic_steps

    def test_columns(self):
        spec = PARSED_TABLES["trajectories"]
        columns = spec.ordered_columns
        # the order of the trajectories already in production
        assert columns[:4] == ["has_full_output", "identifier", "run_type", "task_type"]
        assert columns[4:] == sorted(columns[4:])
        assert set(columns) == spec.columns
        assert {
            "energy_convergence",
            "e_fr_energy_convergence",
            "e_wo_entrp_convergence",
            "forces_convergence",
            "has_full_output",
        } <= set(columns)
        # the properties which are not stored are not columns
        assert "ionic_step_properties" not in columns

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_arrow_roundtrip(self, trajectory):
        spec = PARSED_TABLES["trajectories"]
        schema = pa.schema(arrowize(TrajectoryRow))
        row = TrajectoryRow.from_trajectory(trajectory)
        table = pa.Table.from_pylist([row.model_dump()], schema=schema).select(
            spec.ordered_columns
        )
        assert table.column_names == spec.ordered_columns
        assert table["has_full_output"].type == pa.bool_()
        assert table["energy_convergence"].type == pa.list_(pa.float64())
        # trajectories are not downcast to float32
        assert table["energy"].type == pa.list_(pa.float64())

        restored = TrajectoryRow(**table.to_pylist(maps_as_pydicts="strict")[0])
        assert_nested_close(restored, row)


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
    """The trajectory row stores properties of its parent as columns, which pydantic warns about.

    That is intended, and is silenced for that field only. This runs in a new
    interpreter, as the warning is only raised when the class is defined.
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
    assert "shadows an attribute" not in result.stderr


def test_the_row_stores_the_value_of_the_property():
    """The field shadows RelaxTrajectory.has_full_output, and the two must agree."""
    assert "has_full_output" in TrajectoryRow.model_fields
    assert isinstance(
        RelaxTrajectory.__dict__["has_full_output"], property
    ), "the parent defines it as a property: this is the shadowing which is silenced"
