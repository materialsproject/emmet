"""Test the rows of the DOS and band structure tables: what they hold, and that they rebuild."""

from datetime import UTC, datetime

import numpy as np
import pytest
from pydantic import ValidationError

from emmet.core import ARROW_COMPATIBLE
from emmet.core.band_theory import BSPathType
from emmet.core.io.pymatgen import (
    BandStructureSymmLine,
    CompleteDos,
    Dos,
    Orbital,
    OrbitalType,
    Spin,
    Vasprun,
)
from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.vasp.parse import DirectorySource, parse_calculation
from emmet.core.vasp.parsed import (
    PARSED_TABLES,
    BandStructureProjectionsRow,
    BandStructureRow,
    DosProjectionsRow,
    DosRow,
    SpinMode,
    _label_kpoints,
    _projection_orbitals,
    split_dos_row,
)

if ARROW_COMPATIBLE:
    import io

    import pyarrow as pa
    import pyarrow.parquet as pq

    from emmet.core.arrow import arrowize

COMPLETED_AT = datetime(2020, 3, 11, 1, 50, 16, tzinfo=UTC)
HEADER = {
    "identifier": "mp-1",
    "completed_at": COMPLETED_AT,
    "run_type": RunType.GGA,
    "task_type": TaskType.Static,
    "formula_pretty": "Si",
    "chemsys": "Si",
}


def parse_rows(fixture):
    """The rows of a calculation, and the directory it was parsed from (until it is removed)."""
    with DataArchive.extract(TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz") as d:
        (source,) = DirectorySource.from_directory(d)
        parsed = parse_calculation(source, "aaaaaaab")
        rows = dict(parsed.objects())
        vasprun = Vasprun(
            d / "vasprun.xml.gz", parse_potcar_file=False, parse_projected_eigen=True
        )
    assert parsed.errors == []
    return rows, vasprun


@pytest.fixture(scope="module")
def mesh():
    """Unpolarized, on a uniform mesh."""
    return parse_rows("Si_uniform")


@pytest.fixture(scope="module")
def magnetic():
    """Collinear spin."""
    return parse_rows("magnetic_run")


@pytest.fixture(scope="module")
def path():
    """Self-consistent, with a path of k-points."""
    return parse_rows("r2scan_scf_line")


def integrated_at_fermi_level(row):
    total = (
        np.asarray(row.integrated)
        if row.integrated is not None
        else np.asarray(row.integrated_up) + np.asarray(row.integrated_down)
    )
    return np.interp(row.efermi, row.energies, total)


class TestDos:
    def test_unpolarized(self, mesh):
        rows, vasprun = mesh
        row = rows["total-dos"]
        assert row.spin_mode == SpinMode.UNPOLARIZED
        assert row.density is not None and row.density_up is None
        assert row.integrated is not None and row.integrated_up is None
        np.testing.assert_allclose(
            row.density, vasprun.complete_dos.densities[Spin.up], rtol=1e-6
        )
        np.testing.assert_allclose(
            row.energies, vasprun.complete_dos.energies, atol=2e-6
        )
        assert row.efermi == vasprun.efermi

    def test_collinear_has_a_column_for_each_spin(self, magnetic):
        rows, vasprun = magnetic
        row = rows["total-dos"]
        assert row.spin_mode == SpinMode.COLLINEAR
        assert row.density is None and row.integrated is None
        for spin, name in ((Spin.up, "up"), (Spin.down, "down")):
            np.testing.assert_allclose(
                getattr(row, f"density_{name}"),
                vasprun.complete_dos.densities[spin],
                rtol=1e-6,
            )
            assert getattr(row, f"integrated_{name}") is not None

    @pytest.mark.parametrize("fixture", ["mesh", "magnetic", "path"])
    def test_the_integrated_dos_counts_the_electrons(self, fixture, request):
        """The integrated DOS is the number of electrons at the Fermi level."""
        rows, vasprun = request.getfixturevalue(fixture)
        row = rows["total-dos"]
        assert row.nelect == vasprun.parameters["NELECT"]
        assert integrated_at_fermi_level(row) == pytest.approx(row.nelect, abs=1e-3)

    def test_the_settings_are_those_of_the_calculation(self, mesh, magnetic):
        rows, vasprun = mesh
        row = rows["total-dos"]
        parameters = vasprun.parameters
        assert (row.ispin, row.nbands, row.ismear, row.lorbit) == (
            parameters["ISPIN"],
            parameters["NBANDS"],
            parameters["ISMEAR"],
            parameters["LORBIT"],
        )
        assert row.sigma == parameters["SIGMA"]
        assert (row.ispin, rows["bandstructures"].ispin) == (1, 1)
        assert magnetic[0]["total-dos"].ispin == 2

    def test_the_structure_is_stored_as_its_sites(self, mesh):
        rows, vasprun = mesh
        row = rows["total-dos"]
        assert row.structure == vasprun.final_structure
        assert row.species == ["Si", "Si"]
        assert not hasattr(row, "projected_densities")

    def test_no_integrated_dos_is_allowed(self, mesh):
        rows, vasprun = mesh
        row = DosRow.from_pmg(vasprun.complete_dos, **HEADER)
        assert row.integrated is None and row.density is not None

    def test_to_pmg(self, magnetic):
        rows, vasprun = magnetic
        dos = rows["total-dos"].to_pmg()
        assert type(dos) is Dos
        for spin, densities in vasprun.complete_dos.densities.items():
            np.testing.assert_allclose(dos.densities[spin], densities, rtol=1e-6)
        complete = rows["total-dos"].to_pmg(rows["projected-dos"])
        assert isinstance(complete, CompleteDos)

    def test_a_dos_needs_a_structure(self, mesh):
        _, vasprun = mesh
        dos = Dos(vasprun.efermi, np.array([0.0, 1.0]), {Spin.up: np.array([0.0, 1.0])})
        with pytest.raises(ValueError, match="needs a structure"):
            DosRow.from_pmg(dos, **HEADER)

    def test_lengths_are_checked(self, mesh):
        row = mesh[0]["total-dos"]
        config = row.model_dump()
        config["density"] = config["density"][:-1]
        with pytest.raises(ValidationError, match="number of energies"):
            DosRow(**config)

    def test_noncollinear_is_one_set_of_columns(self, mesh):
        """Only the parameters tell a noncollinear calculation from an unpolarized one."""
        _, vasprun = mesh
        row = DosRow.from_pmg(
            vasprun.complete_dos,
            idos=vasprun.idos,
            parameters={"LNONCOLLINEAR": True},
            **HEADER,
        )
        assert row.spin_mode == SpinMode.NONCOLLINEAR
        assert row.density is not None and row.density_up is None


class TestSpinColumns:
    def test_a_collinear_row_needs_both_spins(self, magnetic):
        config = magnetic[0]["total-dos"].model_dump()
        config["density_down"] = None
        with pytest.raises(ValidationError, match="density_down"):
            DosRow(**config)

    def test_columns_of_another_mode_are_refused(self, mesh):
        config = mesh[0]["total-dos"].model_dump()
        config["density_up"] = config["density"]
        with pytest.raises(ValidationError, match="unpolarized"):
            DosRow(**config)

    def test_projections_follow_the_same_rule(self, mesh):
        config = mesh[0]["projected-dos"].model_dump()
        config["spin_mode"] = SpinMode.COLLINEAR
        with pytest.raises(ValidationError, match="collinear"):
            DosProjectionsRow(**config)


class TestProjectedDos:
    @pytest.mark.parametrize("fixture", ["mesh", "magnetic"])
    def test_the_grid_is_that_of_pymatgen(self, fixture, request):
        rows, vasprun = request.getfixturevalue(fixture)
        row = rows["projected-dos"]
        pdos = vasprun.complete_dos.pdos
        n_orbitals = len(row.orbitals)
        assert row.orbitals[:4] == ["s", "py", "pz", "px"] and n_orbitals == 9
        assert row.shape == [
            len(vasprun.final_structure),
            n_orbitals,
            len(vasprun.complete_dos.energies),
        ]
        for spin in vasprun.complete_dos.densities:
            name = {Spin.up: "up", Spin.down: "down"}[spin]
            column = (
                f"density_{name}" if row.spin_mode == SpinMode.COLLINEAR else "density"
            )
            grid = np.asarray(getattr(row, column)).reshape(row.shape)
            for i, site in enumerate(vasprun.final_structure):
                for j, orbital in enumerate(row.orbitals):
                    np.testing.assert_allclose(
                        grid[i, j], pdos[site][Orbital[orbital]][spin], rtol=1e-6
                    )

    def test_it_is_not_a_column_of_the_total_dos(self, mesh):
        total = mesh[0]["total-dos"]
        assert not {"projected_densities", "density_projections"} & set(
            total.model_dump()
        )

    def test_orbitals_of_lorbit_10_are_types_of_orbital(self, mesh):
        rows, vasprun = mesh
        structure = vasprun.final_structure
        config = {
            "spin_mode": SpinMode.UNPOLARIZED,
            "orbitals": ["s", "p", "d"],
            "shape": [2, 3, 4],
            "density": np.arange(24, dtype=float),
            **HEADER,
        }
        pdos = DosProjectionsRow(**config).to_pdos(structure, 4)
        assert set(pdos[structure[0]]) == {OrbitalType.s, OrbitalType.p, OrbitalType.d}
        np.testing.assert_array_equal(
            pdos[structure[1]][OrbitalType.d][Spin.up], [20, 21, 22, 23]
        )

    def test_the_shape_is_checked(self, mesh):
        config = mesh[0]["projected-dos"].model_dump()
        config["shape"] = [2, 8, 5326]
        with pytest.raises(ValidationError, match="orbitals"):
            DosProjectionsRow(**config)
        config["shape"] = [3, 9, 5326]
        with pytest.raises(ValidationError, match="size of the shape"):
            DosProjectionsRow(**config)

    def test_projections_must_fit_the_dos(self, mesh):
        rows, vasprun = mesh
        row, projections = split_dos_row(
            DosRow.from_pmg(vasprun.complete_dos, **HEADER)
        )
        shorter = DosRow(**{**row.model_dump(), "energies": [0.0], "density": [0.0]})
        with pytest.raises(ValueError, match="does not fit"):
            shorter.to_pmg(projections)


class TestBandStructure:
    def test_mesh(self, mesh):
        rows, vasprun = mesh
        row = rows["bandstructures"]
        pmg_bs = vasprun.get_band_structure(efermi="smart")
        assert row.path_convention == BSPathType.uniform
        assert row.kpath is None and row.kpoint_labels is None
        assert row.shape == [16, 29] == list(pmg_bs.bands[Spin.up].shape)
        np.testing.assert_allclose(
            np.asarray(row.bands).reshape(row.shape), pmg_bs.bands[Spin.up], atol=1e-5
        )
        np.testing.assert_allclose(
            row.kpoint_weights, vasprun.actual_kpoints_weights, rtol=1e-12
        )
        assert sum(row.kpoint_weights) == pytest.approx(1.0)
        assert row.band_gap == pytest.approx(pmg_bs.get_band_gap()["energy"])
        assert row.is_direct is False
        np.testing.assert_allclose(
            row.reciprocal_lattice, pmg_bs.lattice_rec.matrix, rtol=1e-12
        )

    def test_path(self, path):
        rows, vasprun = path
        row = rows["bandstructures"]
        assert row.path_convention == BSPathType.latimer_munro
        # the path has no weights
        assert row.kpoint_weights is None
        n_kpoints = len(row.qpoints)
        assert len(row.kpoint_labels) == n_kpoints and row.shape[1] == n_kpoints
        labels = [label for label in row.kpoint_labels if label]
        assert labels[:6] == ["d", "e", "e", "Γ", "Γ", "d"]
        # a label of the end of a segment and of the start of the next stay in place
        assert row.kpoint_labels[0] == "d" and row.kpoint_labels[-1] is not None

    def test_collinear(self, magnetic):
        rows, vasprun = magnetic
        row = rows["bandstructures"]
        assert row.spin_mode == SpinMode.COLLINEAR
        assert row.bands is None
        pmg_bs = vasprun.get_band_structure()
        for spin, name in ((Spin.up, "up"), (Spin.down, "down")):
            np.testing.assert_allclose(
                np.asarray(getattr(row, f"bands_{name}")).reshape(row.shape),
                pmg_bs.bands[spin],
                atol=1e-5,
            )

    def test_projections_row(self, mesh):
        rows, vasprun = mesh
        row = rows["projected-bandstructures"]
        # the axes are band, k-point, orbital, site
        assert row.shape == [16, 29, 9, 2]
        assert row.orbitals == [Orbital(i).name for i in range(9)]
        expected = vasprun.get_band_structure(efermi="smart").projections[Spin.up]
        np.testing.assert_allclose(
            np.asarray(row.weights).reshape(row.shape), expected, atol=1e-6
        )

    def test_rebuild_a_mesh(self, mesh):
        rows, vasprun = mesh
        rebuilt = rows["bandstructures"].to_pmg(rows["projected-bandstructures"])
        assert type(rebuilt).__name__ == "BandStructure"
        assert rebuilt.projections[Spin.up].shape == (16, 29, 9, 2)
        np.testing.assert_allclose(rebuilt.efermi, vasprun.efermi)

    def test_rebuild_a_path(self, path):
        """The branches and labels come back as they were calculated."""
        rows, vasprun = path
        row = rows["bandstructures"]
        original = vasprun_path_band_structure(path)
        rebuilt = row.to_pmg(rows["projected-bandstructures"])
        assert isinstance(rebuilt, BandStructureSymmLine)
        assert set(rebuilt.labels_dict) == set(original.labels_dict)
        assert [b["name"] for b in rebuilt.branches] == [
            b["name"] for b in original.branches
        ]
        assert [(b["start_index"], b["end_index"]) for b in rebuilt.branches] == [
            (b["start_index"], b["end_index"]) for b in original.branches
        ]
        np.testing.assert_allclose(
            rebuilt.bands[Spin.up], original.bands[Spin.up], atol=1e-5
        )
        assert [k.label for k in rebuilt.kpoints] == [k.label for k in original.kpoints]

    def test_projections_must_fit_the_bands(self, mesh):
        rows, _ = mesh
        config = rows["projected-bandstructures"].model_dump()
        config["shape"] = [16, 28, 9, 2]
        config["weights"] = config["weights"][: 16 * 28 * 9 * 2]
        with pytest.raises(ValueError, match="do not fit|does not fit"):
            rows["bandstructures"].to_pmg(BandStructureProjectionsRow(**config))

    @pytest.mark.parametrize(
        "change, match",
        [
            ({"shape": [16, 28]}, "k-points"),
            ({"kpoint_weights": [1.0]}, "number of k-points"),
            ({"kpoint_labels": ["a"]}, "number of k-points"),
        ],
    )
    def test_the_shape_is_checked(self, mesh, change, match):
        config = {**mesh[0]["bandstructures"].model_dump(), **change}
        if "kpoint_labels" in change or "kpoint_weights" in change:
            config["shape"] = mesh[0]["bandstructures"].shape
        with pytest.raises(ValidationError, match=match):
            BandStructureRow(**config)

    def test_a_band_structure_needs_a_structure(self, mesh):
        _, vasprun = mesh
        band_structure = vasprun.get_band_structure(efermi="smart")
        band_structure.structure = None
        with pytest.raises(ValueError, match="needs a structure"):
            BandStructureRow.from_pmg(band_structure, **HEADER)


def vasprun_path_band_structure(path):
    """The band structure along the path, as pymatgen reads it."""
    from emmet.core.vasp.calculation import _parse_bandstructure_file

    with DataArchive.extract(TEST_FILES_DIR / "vasp" / "r2scan_scf_line.json.gz") as d:
        vasprun = Vasprun(d / "vasprun.xml.gz", parse_potcar_file=False)
        return _parse_bandstructure_file(
            "auto",
            d / "vasprun.xml.gz",
            dict(vasprun.incar),
            use_emmet_models=False,
            kpoints_file=d / "KPOINTS.gz",
            line_mode=True,
            strict_line_mode=True,
        )


class TestHelpers:
    @pytest.mark.parametrize(
        "count, first, last",
        [(9, "s", "dx2_y2"), (16, "s", "f3"), (3, "s", "d"), (4, "s", "f")],
    )
    def test_orbitals_of_the_projections(self, count, first, last):
        names = _projection_orbitals(count)
        assert len(names) == count and (names[0], names[-1]) == (first, last)

    def test_other_counts_are_refused(self):
        with pytest.raises(ValueError, match="not known"):
            _projection_orbitals(10)

    def test_labels_by_coordinates(self):
        qpoints = [[0, 0, 0], [0.25, 0, 0], [0.5, 0, 0], [0.5, 0, 0], [0.9, 0, 0]]
        labels = {"G": [0, 0, 0], "X": [0.5, 0, 0], "Y": [0.5, 0, 0]}
        # a k-point on two labels has the last, as in pymatgen
        assert _label_kpoints(qpoints, labels) == ["G", None, "Y", "Y", None]
        assert _label_kpoints(qpoints, {}) is None
        assert _label_kpoints(qpoints, {"Z": [0.1, 0.1, 0.1]}) is None


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
class TestWritten:
    @pytest.mark.parametrize(
        "table",
        ["total-dos", "projected-dos", "bandstructures", "projected-bandstructures"],
    )
    def test_encodings_of_written_files(self, mesh, table):
        """The floats of 32 bits are byte-stream split, nothing which is a float has a dictionary."""
        spec = PARSED_TABLES[table]
        row = mesh[0][table]
        schema = pa.schema(arrowize(spec.row_model))
        schema = pa.schema([schema.field(c) for c in spec.ordered_columns])
        arrow_table = pa.Table.from_pylist(
            [row.model_dump(context={"format": "arrow"})], schema=schema
        )
        buffer = io.BytesIO()
        pq.write_table(arrow_table, buffer, compression="zstd", **spec.parquet_options)
        metadata = pq.ParquetFile(io.BytesIO(buffer.getvalue())).metadata.row_group(0)
        encodings = {
            metadata.column(i).path_in_schema: set(metadata.column(i).encodings)
            for i in range(metadata.num_columns)
        }
        for path, dtype in spec._leaf_columns():
            if pa.types.is_float32(dtype):
                assert "BYTE_STREAM_SPLIT" in encodings[path], path
            if pa.types.is_floating(dtype):
                assert (
                    not {"PLAIN_DICTIONARY", "RLE_DICTIONARY"} & encodings[path]
                ), path

    @pytest.mark.parametrize("fixture", ["mesh", "magnetic", "path"])
    def test_rows_fit_their_tables_and_survive(self, fixture, request):
        rows, _ = request.getfixturevalue(fixture)
        for table, row in rows.items():
            if table not in PARSED_TABLES or "dos" not in table and "band" not in table:
                continue
            spec = PARSED_TABLES[table]
            schema = pa.schema(arrowize(spec.row_model))
            arrow_table = pa.Table.from_pylist(
                [row.model_dump(context={"format": "arrow"})], schema=schema
            )
            restored = type(row)(**arrow_table.to_pylist(maps_as_pydicts="strict")[0])
            for name in type(row).model_fields:
                before, after = getattr(row, name), getattr(restored, name)
                if isinstance(before, list) and before and isinstance(before[0], float):
                    np.testing.assert_allclose(after, before, rtol=1e-6, atol=1e-6)
