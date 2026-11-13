"""Test the models of the tables of volumetric data: each kind of data has its own."""

from datetime import UTC, datetime

import numpy as np
import pytest

from emmet.core import ARROW_COMPATIBLE
from emmet.core.io.pymatgen import Chgcar, Elfcar, Locpot
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.vasp.models import Pot
from emmet.core.vasp.parsed import (
    PARSED_TABLES,
    VOLUMETRIC_FILE_MODELS,
    AllElectronDensityRow,
    ChargeDensityRow,
    ElectronLocalizationRow,
    LocalPotentialRow,
    PartialChargeDensityRow,
    SpinMode,
    VolumetricGridRow,
    parchg_indices,
)

if ARROW_COMPATIBLE:
    import io

    import pyarrow as pa
    import pyarrow.parquet as pq

    from emmet.core.arrow import arrowize

GRID = (2, 2, 3)


def header(**overrides):
    return {
        "identifier": "mp-1",
        "completed_at": datetime(2020, 3, 11, tzinfo=UTC),
        "run_type": RunType.GGA,
        "task_type": TaskType.Static,
        "formula_pretty": "CsCl",
        "chemsys": "Cl-Cs",
        **overrides,
    }


def written_encodings(table, **options):
    """The encodings of each column of a Parquet file written from a table."""
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd", **options)
    metadata = pq.ParquetFile(io.BytesIO(buffer.getvalue())).metadata
    group = metadata.row_group(0)
    return {
        group.column(i).path_in_schema: group.column(i).encodings
        for i in range(metadata.num_columns)
    }


def written_statistics(table, **options):
    """Whether each column of a Parquet file written from a table has its min and max."""
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd", **options)
    metadata = pq.ParquetFile(io.BytesIO(buffer.getvalue())).metadata
    group = metadata.row_group(0)
    return {
        group.column(i).path_in_schema: bool(
            group.column(i).statistics is not None
            and group.column(i).statistics.has_min_max
        )
        for i in range(metadata.num_columns)
    }


def block_columns(row):
    """The names of the block columns which have data."""
    return [c for c in row.BLOCK_COLUMNS if getattr(row, c) is not None]


class TestChargeDensity:
    def test_collinear(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["collinear"])
        row = ChargeDensityRow.from_pmg(pmg_obj, file_name="CHGCAR", **header())
        assert row.spin_mode == SpinMode.COLLINEAR
        assert block_columns(row) == ["total", "magnetization"]
        assert row.saxis is None
        assert row.grid_shape == list(GRID)

    def test_unpolarized(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["unpolarized"])
        row = ChargeDensityRow.from_pmg(pmg_obj, file_name="CHGCAR", **header())
        assert row.spin_mode == SpinMode.UNPOLARIZED
        assert block_columns(row) == ["total"]

    def test_noncollinear_does_not_store_the_derived_block(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["noncollinear"])
        # pymatgen adds a block which is not in the file
        assert "diff" in pmg_obj.data
        row = ChargeDensityRow.from_pmg(
            pmg_obj,
            parameters={"SAXIS": [0.0, 1.0, 0.0]},
            file_name="CHGCAR",
            **header(),
        )
        assert row.spin_mode == SpinMode.NONCOLLINEAR
        assert block_columns(row) == [
            "total",
            "magnetization_1",
            "magnetization_2",
            "magnetization_3",
        ]
        assert row.magnetization is None
        # the axes of the components are recorded, as they are not Cartesian in general
        assert row.saxis == [0.0, 1.0, 0.0]

    def test_saxis_is_only_for_noncollinear_calculations(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["collinear"])
        row = ChargeDensityRow.from_pmg(
            pmg_obj, parameters={"SAXIS": [0.0, 0.0, 1.0]}, file_name="C", **header()
        )
        assert row.saxis is None

    @pytest.mark.parametrize(
        "file_key", ["collinear", "unpolarized", "noncollinear", "collinear_no_aug"]
    )
    def test_to_pmg_roundtrip(self, volumetric_files, file_key):
        pmg_obj = Chgcar.from_file(volumetric_files[file_key])
        row = ChargeDensityRow.from_pmg(pmg_obj, file_name="CHGCAR", **header())
        new = row.to_pmg()
        assert isinstance(new, Chgcar)
        # pymatgen's own labels, including the block it computes
        assert set(new.data) == set(pmg_obj.data)
        for key, grid in pmg_obj.data.items():
            assert new.data[key].shape == GRID
            assert np.allclose(new.data[key], grid, rtol=1e-6, atol=1e-6), key
        assert new.structure.matches(pmg_obj.structure)

    def test_grid_is_flattened_with_z_fastest(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["unpolarized"])
        row = ChargeDensityRow.from_pmg(pmg_obj, file_name="CHGCAR", **header())
        grid = pmg_obj.data["total"]
        flat = np.asarray(row.total)
        # grid[ix, iy, iz] is at ix * NY * NZ + iy * NZ + iz
        for ix, iy, iz in ((0, 0, 0), (0, 0, 2), (0, 1, 0), (1, 0, 0), (1, 1, 2)):
            assert flat[ix * GRID[1] * GRID[2] + iy * GRID[2] + iz] == grid[ix, iy, iz]
        assert np.array_equal(flat.reshape(row.grid_shape), grid)
        assert not np.array_equal(flat.reshape(row.grid_shape, order="F"), grid)

    def test_structure_is_the_geometry_of_the_file(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["collinear"])
        row = ChargeDensityRow.from_pmg(pmg_obj, file_name="CHGCAR", **header())
        assert row.species == ["Cs", "Cl"]
        assert np.allclose(row.lattice, pmg_obj.structure.lattice.matrix)
        assert np.allclose(row.frac_coords, pmg_obj.structure.frac_coords)
        assert row.structure.matches(pmg_obj.structure)
        dumped = row.model_dump()
        assert "structure" not in dumped and "data_aug" not in dumped
        assert "data" not in dumped and "labels" not in dumped

    def test_unexpected_blocks_are_an_error(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["collinear"])
        pmg_obj.data["spin_up"] = pmg_obj.data["total"]
        with pytest.raises(ValueError, match="Unexpected blocks"):
            ChargeDensityRow.from_pmg(pmg_obj, file_name="CHGCAR", **header())


class TestAllElectronDensity:
    def test_row(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["unpolarized"])
        row = AllElectronDensityRow.from_pmg(pmg_obj, file_name="AECCAR0", **header())
        assert block_columns(row) == ["total"]
        assert row.spin_mode == SpinMode.UNPOLARIZED
        assert np.allclose(row.to_pmg().data["total"], pmg_obj.data["total"], rtol=1e-6)

    def test_a_second_block_is_a_magnetization(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["collinear"])
        row = AllElectronDensityRow.from_pmg(pmg_obj, file_name="AECCAR2", **header())
        assert block_columns(row) == ["total", "magnetization"]
        assert set(row.to_pmg().data) == {"total", "diff"}

    def test_each_aeccar_has_its_own_table_and_geometry(self):
        for file_type, table in (
            ("AECCAR0", "core-density"),
            ("AECCAR1", "atomic-density"),
            ("AECCAR2", "valence-density"),
        ):
            assert PARSED_TABLES[table].row_model is AllElectronDensityRow
            assert VOLUMETRIC_FILE_MODELS[file_type] is AllElectronDensityRow


class TestLocalPotential:
    def test_collinear_blocks_are_the_two_spins(self, volumetric_files):
        pmg_obj = Locpot.from_file(volumetric_files["collinear_no_aug"])
        row = LocalPotentialRow.from_pmg(pmg_obj, file_name="LOCPOT", **header())
        assert block_columns(row) == ["spin_up", "spin_down"]
        assert row.spin_mode == SpinMode.COLLINEAR
        new = row.to_pmg()
        assert isinstance(new, Locpot)
        assert set(new.data) == {"spin_up", "spin_down"}
        assert np.allclose(new.data["spin_up"], pmg_obj.data["spin_up"], rtol=1e-6)

    def test_unpolarized(self, volumetric_files):
        pmg_obj = Locpot.from_file(volumetric_files["unpolarized"])
        row = LocalPotentialRow.from_pmg(pmg_obj, file_name="LOCPOT", **header())
        assert block_columns(row) == ["potential"]

    def test_noncollinear_blocks_are_a_scalar_and_a_b_field(self, volumetric_files):
        pmg_obj = Locpot.from_file(volumetric_files["noncollinear"])
        row = LocalPotentialRow.from_pmg(
            pmg_obj,
            parameters={"SAXIS": [0.0, 0.0, 1.0]},
            file_name="LOCPOT",
            **header(),
        )
        assert block_columns(row) == [
            "potential",
            "b_field_1",
            "b_field_2",
            "b_field_3",
        ]
        assert row.spin_mode == SpinMode.NONCOLLINEAR
        assert row.saxis == [0.0, 0.0, 1.0]
        # no magnetization columns: a potential has none
        assert not hasattr(row, "magnetization")

    def test_pot_is_read_like_a_locpot(self, volumetric_files):
        pmg_obj = Pot.from_file(volumetric_files["pot_collinear"])
        row = LocalPotentialRow.from_pmg(pmg_obj, file_name="POT", **header())
        assert block_columns(row) == ["spin_up", "spin_down"]
        assert "data_aug" not in row.model_dump()
        assert VOLUMETRIC_FILE_MODELS["POT"] is LocalPotentialRow

    @pytest.mark.parametrize(
        "parameters, kind",
        [
            ({"LVTOT": True, "LVHAR": False}, "total"),
            ({"LVTOT": False, "LVHAR": True}, "electrostatic"),
            # LVHAR sets LVTOT false, whatever it says
            ({"LVTOT": True, "LVHAR": True}, "electrostatic"),
            ({"LVTOT": False, "LVHAR": False}, None),
            ({"WRT_POTENTIAL": "total"}, "total"),
            ({"WRT_POTENTIAL": "hartree ionic"}, None),
            ({"WRT_POTENTIAL": "hartree total"}, "total"),
            ({}, None),
        ],
    )
    def test_potential_kind(self, volumetric_files, parameters, kind):
        pmg_obj = Locpot.from_file(volumetric_files["unpolarized"])
        row = LocalPotentialRow.from_pmg(
            pmg_obj, parameters=parameters, file_name="LOCPOT", **header()
        )
        assert row.potential_kind == kind
        # the tags it comes from are kept
        assert row.lvtot == parameters.get("LVTOT")
        assert row.lvhar == parameters.get("LVHAR")

    def test_wrt_potential_is_a_list(self, volumetric_files):
        pmg_obj = Locpot.from_file(volumetric_files["unpolarized"])
        row = LocalPotentialRow.from_pmg(
            pmg_obj,
            parameters={"WRT_POTENTIAL": "hartree total"},
            file_name="LOCPOT",
            **header(),
        )
        assert row.wrt_potential == ["hartree", "total"]


class TestElectronLocalization:
    def test_unpolarized(self, volumetric_files):
        pmg_obj = Elfcar.from_file(volumetric_files["unpolarized"])
        row = ElectronLocalizationRow.from_pmg(pmg_obj, file_name="ELFCAR", **header())
        assert block_columns(row) == ["elf"]
        new = row.to_pmg()
        assert isinstance(new, Elfcar)
        assert np.allclose(new.data["total"], pmg_obj.data["total"], rtol=1e-6)

    def test_collinear_blocks_are_the_two_spins(self, volumetric_files):
        pmg_obj = Elfcar.from_file(volumetric_files["collinear_no_aug"])
        row = ElectronLocalizationRow.from_pmg(pmg_obj, file_name="ELFCAR", **header())
        assert block_columns(row) == ["elf_up", "elf_down"]
        assert set(row.to_pmg().data) == {"spin_up", "spin_down"}

    def test_it_is_not_implemented_for_noncollinear_calculations(
        self, volumetric_files
    ):
        pmg_obj = Elfcar.from_file(volumetric_files["noncollinear"])
        with pytest.raises(ValueError, match="Unexpected blocks"):
            ElectronLocalizationRow.from_pmg(pmg_obj, file_name="ELFCAR", **header())


class TestPartialChargeDensity:
    @pytest.mark.parametrize(
        "file_name, indices",
        [
            ("PARCHG", (None, None)),
            ("PARCHG.gz", (None, None)),
            ("PARCHG.0003.0002", (3, 2)),
            ("PARCHG.0003.ALLK", (3, None)),
            ("PARCHG.ALLB.0002", (None, 2)),
            ("PARCHG.ALLB.ALLK", (None, None)),
            ("PARCHG.0010.0002.relax1.gz", (10, 2)),
            ("PARCHG.0003.ALLK.static", (3, None)),
            ("block/launcher/PARCHG.0001.0001", (1, 1)),
        ],
    )
    def test_indices(self, file_name, indices):
        assert parchg_indices(file_name) == indices

    def test_row(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["collinear"])
        parameters = {
            "LSEPB": True,
            "LSEPK": False,
            "IBAND": [10, 11],
            "KPUSE": [1, 2, 3],
            "EINT": [-1.0, 0.0],
            "NBMOD": -3,
            "SAXIS": [0.0, 0.0, 1.0],
        }
        row = PartialChargeDensityRow.from_pmg(
            pmg_obj, parameters=parameters, file_name="PARCHG.0010.ALLK", **header()
        )
        assert (row.band_index, row.kpoint_index) == (10, None)
        assert row.iband == [10, 11] and row.kpuse == [1, 2, 3]
        assert row.eint == [-1.0, 0.0] and row.nbmod == -3
        assert row.lsepb is True and row.lsepk is False
        # it has the blocks and units of a charge density
        assert block_columns(row) == ["total", "magnetization"]
        assert isinstance(row.to_pmg(), Chgcar)

    def test_scalar_selections_are_lists(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["unpolarized"])
        row = PartialChargeDensityRow.from_pmg(
            pmg_obj,
            parameters={"IBAND": 5, "KPUSE": 2},
            file_name="PARCHG",
            **header(),
        )
        assert row.iband == [5] and row.kpuse == [2]
        assert row.eint is None and row.nbmod is None

    def test_without_parameters(self, volumetric_files):
        pmg_obj = Chgcar.from_file(volumetric_files["unpolarized"])
        row = PartialChargeDensityRow.from_pmg(pmg_obj, file_name="PARCHG", **header())
        assert row.iband is None and row.lsepb is None


class TestTableLayout:
    def test_models_explain_themselves(self):
        """Every column of every table of volumetric data is described, and its units given."""
        for table, spec in PARSED_TABLES.items():
            if spec.row_model.__name__ not in {
                "ChargeDensityRow",
                "PartialChargeDensityRow",
                "AllElectronDensityRow",
                "LocalPotentialRow",
                "ElectronLocalizationRow",
            }:
                continue
            for name, field in spec.row_model.model_fields.items():
                assert field.description, f"{table}.{name} has no description"
            doc = spec.row_model.__doc__ or ""
            assert "http" in doc or "VASP" in doc, table

    def test_units_and_grid_order_are_documented(self):
        # densities are stored as n(r) * V_cell, potentials in eV, ELF has no unit
        assert "n(r) * V_cell" in ChargeDensityRow.__doc__
        assert "n(r) * V_cell" in AllElectronDensityRow.__doc__
        assert "in eV" in LocalPotentialRow.__doc__
        assert "dimensionless" in ElectronLocalizationRow.__doc__
        # the order of the grid is stated where all the models share it
        assert "z varies fastest" in VolumetricGridRow.__doc__
        assert "VASP writes the values" in VolumetricGridRow.__doc__

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    @pytest.mark.parametrize(
        "model, file_key, pmg_cls",
        [
            (ChargeDensityRow, "collinear", Chgcar),
            (ChargeDensityRow, "noncollinear", Chgcar),
            (AllElectronDensityRow, "unpolarized", Chgcar),
            (LocalPotentialRow, "collinear_no_aug", Locpot),
            (LocalPotentialRow, "noncollinear", Locpot),
            (ElectronLocalizationRow, "unpolarized", Elfcar),
        ],
    )
    def test_arrow_roundtrip(self, volumetric_files, model, file_key, pmg_cls):
        pmg_obj = pmg_cls.from_file(volumetric_files[file_key])
        row = model.from_pmg(pmg_obj, file_name="FILE", **header())
        schema = pa.schema(arrowize(model))
        table = pa.Table.from_pylist([row.model_dump()], schema=schema)
        for column in model.BLOCK_COLUMNS:
            assert table[column].type == pa.large_list(pa.float32())
        restored = model(**table.to_pylist()[0])
        assert restored.spin_mode == row.spin_mode
        assert restored.grid_shape == row.grid_shape
        assert block_columns(restored) == block_columns(row)
        for column in block_columns(row):
            assert np.allclose(
                getattr(restored, column), getattr(row, column), rtol=1e-6, atol=1e-6
            )

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_grids_use_byte_stream_split(self, volumetric_files):
        """The encoding is applied, not only requested: a writer ignores unknown paths."""
        spec = PARSED_TABLES["charge-density"]
        assert spec.byte_stream_split_columns == [
            f"{c}.list.element" for c in ChargeDensityRow.BLOCK_COLUMNS
        ]
        pmg_obj = Chgcar.from_file(volumetric_files["collinear"])
        row = ChargeDensityRow.from_pmg(pmg_obj, file_name="CHGCAR", **header())
        table = pa.Table.from_pylist(
            [row.model_dump()], schema=pa.schema(arrowize(spec.row_model))
        )
        encodings = written_encodings(table, **spec.parquet_options)
        for path in ("total.list.element", "magnetization.list.element"):
            assert "BYTE_STREAM_SPLIT" in encodings[path], path
        # only the floats of 32 bits: the lattice and the coordinates are doubles
        assert "BYTE_STREAM_SPLIT" not in encodings["lattice.list.element.list.element"]
        # and the rest keep dictionary encoding
        assert "RLE_DICTIONARY" in encodings["species.list.element"]

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_byte_stream_split_needs_dictionary_encoding_off(self, volumetric_files):
        """With both, the dictionary wins, and BYTE_STREAM_SPLIT is silently ignored."""
        spec = PARSED_TABLES["charge-density"]
        pmg_obj = Chgcar.from_file(volumetric_files["collinear"])
        row = ChargeDensityRow.from_pmg(pmg_obj, file_name="CHGCAR", **header())
        table = pa.Table.from_pylist(
            [row.model_dump()], schema=pa.schema(arrowize(spec.row_model))
        )
        encodings = written_encodings(
            table, use_byte_stream_split=spec.byte_stream_split_columns
        )
        assert "BYTE_STREAM_SPLIT" not in encodings["total.list.element"]

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    @pytest.mark.parametrize("table", sorted(PARSED_TABLES))
    def test_parquet_options_name_real_columns(self, table):
        """Every path in the options is a column of the file written, for every table."""
        spec = PARSED_TABLES[table]
        schema = pa.schema(arrowize(spec.row_model))
        schema = pa.schema([schema.field(c) for c in spec.ordered_columns])
        arrow_table = pa.Table.from_pylist(
            [{f.name: None for f in schema}], schema=schema
        )
        options = spec.parquet_options
        encodings = written_encodings(arrow_table, **options)

        requested = set(options["use_byte_stream_split"]) | set(
            options["use_dictionary"]
        )
        doubles = {
            path for path, dtype in spec._leaf_columns() if pa.types.is_float64(dtype)
        }
        assert requested | doubles == set(encodings)
        assert not requested & doubles
        assert not set(options["use_byte_stream_split"]) & set(
            options["use_dictionary"]
        )
        # a dictionary is of no use to a double, so they are not encoded with one
        for path in doubles:
            assert not {"PLAIN_DICTIONARY", "RLE_DICTIONARY"} & set(encodings[path])
        for path in options["use_byte_stream_split"]:
            assert "BYTE_STREAM_SPLIT" in encodings[path], path
        assert not {p for p, e in encodings.items() if "BYTE_STREAM_SPLIT" in e} - set(
            options["use_byte_stream_split"]
        )

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    @pytest.mark.parametrize(
        "table, columns",
        [
            (
                "total-dos",
                [
                    "energies.list.element",
                    *(
                        f"{c}{s}.list.element"
                        for c in ("density", "integrated")
                        for s in ("", "_up", "_down")
                    ),
                ],
            ),
            (
                "projected-dos",
                [f"density{s}.list.element" for s in ("", "_up", "_down")],
            ),
            (
                "projected-bandstructures",
                [f"weights{s}.list.element" for s in ("", "_up", "_down")],
            ),
            (
                "bandstructures",
                [f"bands{s}.list.element" for s in ("", "_up", "_down")],
            ),
        ],
    )
    def test_every_float32_column_is_split(self, table, columns):
        assert set(columns) <= set(PARSED_TABLES[table].byte_stream_split_columns)
        # none of the tables' doubles are
        assert not any(
            c.startswith(("efermi", "qpoints", "lattice", "frac_coords"))
            for c in PARSED_TABLES[table].byte_stream_split_columns
        )


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
class TestStatistics:
    """Min and max are written for the columns that are filtered on, and not for the rest."""

    @pytest.mark.parametrize("table", sorted(PARSED_TABLES))
    def test_statistics_are_requested_for_leaves_of_the_file_only(self, table):
        """A writer ignores paths that are not in the file, without an error."""
        spec = PARSED_TABLES[table]
        schema = pa.schema(arrowize(spec.row_model))
        schema = pa.schema([schema.field(c) for c in spec.ordered_columns])
        written = written_statistics(
            pa.Table.from_pylist([{f.name: None for f in schema}], schema=schema),
            **spec.parquet_options,
        )
        wanted = set(spec.statistics_columns)
        assert wanted and wanted <= set(written)
        # nothing inside a list or map, and no JSON string, has a minimum
        for path in wanted:
            assert ".list." not in path and ".key_value." not in path, path
            assert path not in spec.json_string_columns, path

    def test_the_json_strings_of_the_tasks_table(self):
        assert set(PARSED_TABLES["tasks"].json_string_columns) == {
            "input.incar",
            "input.parameters",
            "orig_inputs.incar",
            "orig_inputs.parameters",
            "transformations",
        }
        for table, spec in PARSED_TABLES.items():
            if table != "tasks":
                assert spec.json_string_columns == []

    def test_json_strings_are_found_by_either_declaration(self):
        """A field typed as JSON, or one that is overridden to be a string, anywhere in a model."""
        from pydantic import BaseModel

        from emmet.core.types.typing import JsonDictType
        from emmet.core.utils import type_override
        from emmet.core.vasp.parsed import TableSpec

        @type_override({"overridden": str})
        class Inner(BaseModel):
            typed: JsonDictType = None
            overridden: dict | None = None
            plain: str | None = None

        class Outer(BaseModel):
            inner: Inner | None = None
            many: list[Inner] | None = None
            typed: JsonDictType = None
            text: str | None = None

        spec = TableSpec("synthetic", Outer)
        assert sorted(spec.json_string_columns) == [
            "inner.overridden",
            "inner.typed",
            "many.list.element.overridden",
            "many.list.element.typed",
            "typed",
        ]

    def test_a_json_string_has_no_statistics_when_written(self):
        """The minimum and maximum of a string of 4 kB are kept in every page and in the footer."""
        spec = PARSED_TABLES["tasks"]
        schema = pa.schema(arrowize(spec.row_model))
        schema = pa.schema([schema.field(c) for c in spec.ordered_columns])
        record = {f.name: None for f in schema}
        record["task_id"] = "aaaaaaab"
        record["input"] = {"parameters": '{"A":' + "1" * 2000 + "}", "incar": "{}"}
        record["calc_suffix"] = "standard"
        table = pa.Table.from_pylist([record], schema=schema)

        statistics = written_statistics(table, **spec.parquet_options)
        assert statistics["task_id"] and statistics["calc_suffix"]
        assert not statistics["input.parameters"] and not statistics["input.incar"]
        # every leaf has them if the rule is not applied
        assert written_statistics(table)["input.parameters"]
        assert len(_written_size(table, **spec.parquet_options)) < len(
            _written_size(table)
        )

    def test_the_other_options_are_kept(self):
        """Statistics are an option of the writer next to the encodings, and do not replace them."""
        options = PARSED_TABLES["charge-density"].parquet_options
        assert set(options) == {
            "use_byte_stream_split",
            "use_dictionary",
            "write_statistics",
        }
        assert "total.list.element" in options["use_byte_stream_split"]
        assert "total.list.element" not in options["write_statistics"]
        assert "identifier" in options["write_statistics"]
        assert "grid_shape.list.element" not in options["write_statistics"]


def _written_size(table, **options):
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd", **options)
    return buffer.getvalue()
