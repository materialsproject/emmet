"""Define the row models of the parsed-tier tables of large VASP objects.

Each model here describes one row of a table: the data of a VASP object (e.g., a
density of states), plus a header of top-level columns used to partition, sort, and
filter the table without joining on other tables. The models do not derive from the
emmet-core models of these objects (e.g., `ElectronicDos`): they are the layout of
a table, which is not that of a document.

Large numeric arrays are flat lists of float32, in C order, with their shape
in a column or defined by the model. The structure of an object is its lattice,
species and fractional coordinates.

The schema of every table is `pa.schema(arrowize(<row model>))`: no schemas
are defined separately from the models. Arrow-specific column types, such as
float32 columns, are declared on the fields of the models themselves.

Importing this module does not require pyarrow. Table construction and I/O
is the responsibility of whatever writes the tables.

Projections are stored apart from the DOS and band structure they belong to,
because they are far larger than the rest of the data and are rarely needed
together with it. A DOS or band structure therefore has two tables, which
are joined on `identifier`: one with the rows of `DosRow` / `BandStructureRow`
(no projections), and one with the rows of `DosProjectionsRow` /
`BandStructureProjectionsRow`. Use `DosRow.to_pmg` / `BandStructureRow.to_pmg`,
with the projections row, to put them back together.

Because the models validate their input, rows should be constructed directly
from pymatgen objects, which avoids copying very large arrays:

    >>> ChargeDensityRow.from_pmg(
    ...     chgcar,
    ...     parameters=vasprun.parameters,
    ...     identifier="mp-1",
    ...     file_name="CHGCAR.relax1.gz",
    ...     completed_at=completed_at,
    ...     run_type=RunType.GGA,
    ...     task_type=TaskType.Static,
    ...     formula_pretty="Si",
    ...     chemsys="Si",
    ... )

and not by dumping an existing model and validating that dump again.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal

import numpy as np

from pydantic import BaseModel, BeforeValidator, Field, PrivateAttr, model_validator

from emmet.core.band_theory import BSPathType, _get_site_indices, infer_path
from emmet.core.tasks import CoreTaskDoc
from emmet.core.trajectory import RelaxTrajectory
from emmet.core.types.enums import ValueEnum
from emmet.core.types.typing import TaskIdentifierType
from emmet.core.utils import convert_datetime, utcnow
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.io.pymatgen import (
    BandStructure as PmgBandStructure,
    BandStructureSymmLine,
    Chgcar,
    CompleteDos,
    Dos,
    Elfcar,
    Lattice,
    Locpot,
    Orbital,
    OrbitalType,
    Spin,
    Structure,
)
from emmet.core.types.arrow_annotations import Float32Grid, Float32List
from emmet.core.vasp.models import volumetric_file_type

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any, Self


def _require_datetime(v: Any) -> datetime:
    """Convert to a timezone-aware datetime, but do not silently default to now."""
    if not v:
        raise ValueError(
            "A completion time is required, it determines the partition of the row."
        )
    return convert_datetime(v)


def _optional_datetime(v: Any) -> datetime | None:
    """Convert to a timezone-aware datetime, or None if there is no value."""
    return convert_datetime(v) if v else None


class ParsedRowHeader(BaseModel):
    """Top-level columns shared by the rows of every table of large VASP objects.

    These are stored on each row, rather than found by joining on the tasks
    table, so that tables can be partitioned, sorted, and filtered on their own.
    The calculation directory and suffix are not repeated here: they are
    stored once in the tasks table, which can be joined on `identifier`.
    """

    identifier: TaskIdentifierType = Field(
        description="The identifier of the calculation. Joins to the task_id "
        "of the tasks table."
    )
    completed_at: Annotated[datetime, BeforeValidator(_require_datetime)] = Field(
        description="When the calculation was completed. Determines the date "
        "partition of the row."
    )
    year: int | None = Field(
        None, description="The year of `completed_at`. Always derived from it."
    )
    month: int | None = Field(
        None, description="The month of `completed_at`. Always derived from it."
    )
    day: int | None = Field(
        None, description="The day of `completed_at`. Always derived from it."
    )
    run_type: RunType = Field(description="The functional used in the calculation.")
    task_type: TaskType = Field(description="The type of calculation.")
    formula_pretty: str = Field(description="The reduced formula of the structure.")
    chemsys: str = Field(
        description="The chemical system of the structure, e.g., Li-Fe-O."
    )

    @model_validator(mode="after")
    def set_partition_date(self) -> Self:
        """Derive the date columns from `completed_at`, so they cannot disagree."""
        self.year = self.completed_at.year
        self.month = self.completed_at.month
        self.day = self.completed_at.day
        return self


class SpinMode(ValueEnum):
    """How the spin of a volumetric file is represented, by its number of blocks."""

    UNPOLARIZED = "unpolarized"
    COLLINEAR = "collinear"
    NONCOLLINEAR = "noncollinear"


_NONCOLLINEAR_BLOCKS = 4


def _spin_mode(num_blocks: int) -> SpinMode:
    """The spin mode of a file, from the number of blocks of data it has."""
    modes = {
        1: SpinMode.UNPOLARIZED,
        2: SpinMode.COLLINEAR,
        _NONCOLLINEAR_BLOCKS: SpinMode.NONCOLLINEAR,
    }
    if num_blocks not in modes:
        raise ValueError(
            f"A volumetric file has 1, 2 or {_NONCOLLINEAR_BLOCKS} blocks, not {num_blocks}."
        )
    return modes[num_blocks]  # type: ignore[return-value]


def _structure_columns(structure: Any) -> dict[str, Any]:
    """The lattice and sites of a structure, which is all that a volumetric file has."""
    return {
        "lattice": structure.lattice.matrix.tolist(),
        "species": [site.species_string for site in structure],
        "frac_coords": structure.frac_coords.tolist(),
    }


class _HasStructure:
    """Gives a row with a `lattice`, `species` and `frac_coords` a pymatgen structure."""

    lattice: list[list[float]]
    species: list[str]
    frac_coords: list[list[float]]

    @property
    def structure(self) -> Structure:
        """The structure of the row, as a pymatgen object."""
        return Structure(self.lattice, self.species, self.frac_coords)


def _flat(grid: Any) -> Any:
    """Flatten a grid indexed by `[ix, iy, iz]` in C order, so that z varies fastest."""
    return np.asarray(grid).flatten(order="C")


class VolumetricGridRow(ParsedRowHeader, _HasStructure):
    """The columns every table of volumetric data (CHGCAR, LOCPOT, ...) has.

    A volumetric file is a structure followed by one or more *blocks*, each a value
    at every point of a uniform real-space grid, which is spanned by the lattice
    vectors: the point `(ix, iy, iz)` is at `ix/NX * a + iy/NY * b + iz/NZ * c`.
    What the blocks are, and their units, depends on the kind of file, and is
    described by the model of each table. The file's own structure is stored as
    its lattice, species and fractional coordinates, which is all it has.
    That is not necessarily the final structure of the calculation.

    The columns of the blocks are `list<float32>`. A block is **flattened in C order
    from an array indexed `[ix, iy, iz]`, so z varies fastest** along the list. It is
    rebuilt with `np.reshape(block, grid_shape)`. VASP writes the values
    of its files with x varying fastest, the opposite order.
    """

    BLOCK_COLUMNS: ClassVar[tuple[str, ...]] = ()
    """The names of the columns which hold a block of data."""

    file_name: str = Field(
        description="The name of the volumetric file, including any calculation "
        "suffix and compression extension, e.g., CHGCAR.relax1.gz"
    )
    spin_mode: SpinMode = Field(
        description="How the spin is represented, which is found from the number "
        "of blocks the file has: one (unpolarized), two (collinear) or four "
        "(noncollinear)."
    )
    grid_shape: list[int] = Field(
        description="The number of grid points along each lattice vector: "
        "(NGXF, NGYF, NGZF), the fine FFT grid. All blocks of a file have it."
    )
    lattice: list[list[float]] = Field(
        description="The lattice vectors a, b, c, as rows, in Angstrom."
    )
    species: list[str] = Field(
        description="The element of each site, in the order of the file."
    )
    frac_coords: list[list[float]] = Field(
        description="The fractional coordinates of each site."
    )

    @classmethod
    def from_pmg(
        cls, pmg_obj: Any, parameters: Any = None, **kwargs: Any
    ) -> VolumetricGridRow:
        """Make a row from the pymatgen object of a file, and the parameters of its calculation.

        `kwargs` are the columns of the header, and `file_name`.
        """
        raise NotImplementedError

    def to_pmg(self, pmg_cls: Any = None) -> Any:
        """Make the pymatgen object of the file, with the labels pymatgen gives its blocks."""
        raise NotImplementedError

    def _grid(self, name: str) -> Any:
        """A block as an array indexed `[ix, iy, iz]`, or None if the row has no such block."""
        flat = getattr(self, name)
        if flat is None:
            return None
        return np.asarray(flat).reshape(self.grid_shape, order="C")

    @staticmethod
    def _blocks_of(pmg_obj: Any) -> dict[str, Any]:
        """The blocks that are in the file, with the names pymatgen gave them.

        pymatgen also adds a block it computes from the others to noncollinear files
        (`diff`, the signed magnitude of the magnetization), which is not in the file.
        """
        data = dict(pmg_obj.data)
        if {"diff_x", "diff_y", "diff_z"} <= set(data):
            data.pop("diff", None)
        return data

    @classmethod
    def _grid_columns(cls, pmg_obj: Any, names: dict[str, str]) -> dict[str, Any]:
        """Flatten the blocks of a pymatgen object into the columns they belong in."""
        data = cls._blocks_of(pmg_obj)
        unknown = set(data).difference(names)
        if unknown:
            raise ValueError(
                f"Unexpected blocks {sorted(unknown)} in a {cls.__name__}, "
                f"expected only {sorted(names)}."
            )
        columns = {names[k]: _flat(v) for k, v in data.items()}
        shape = {np.asarray(v).shape for v in data.values()}
        if len(shape) != 1:
            raise ValueError(f"The blocks have different grids: {sorted(shape)}.")
        return {
            **columns,
            "grid_shape": list(shape.pop()),
            "spin_mode": _spin_mode(len(data)),
            **_structure_columns(pmg_obj.structure),
        }

    def _data_for(self, pmg_names: dict[str, str]) -> dict[str, Any]:
        """The blocks of the row, under the names pymatgen gives them."""
        return {
            pmg_name: grid
            for column, pmg_name in pmg_names.items()
            if (grid := self._grid(column)) is not None
        }

    @staticmethod
    def _with_noncollinear_diff(data: dict[str, Any]) -> dict[str, Any]:
        """Add the block pymatgen computes for noncollinear data, as it does."""
        if {"diff_x", "diff_y", "diff_z"} <= set(data):
            m1, m2, m3 = data["diff_x"], data["diff_y"], data["diff_z"]
            sign = np.sign(m1 * 1.01 + m2 * 1.02 + m3 * 1.03)
            data = {**data, "diff": np.sqrt(m1**2 + m2**2 + m3**2) * sign}
        return data


_SAXIS_DOC = (
    "The spin quantization axis (SAXIS), in which the components of the noncollinear "
    "magnetization are given. They are components along the Cartesian axes only for "
    "the default (0, 0, 1). Null unless the calculation is noncollinear."
)


def _saxis(parameters: Any, spin_mode: SpinMode) -> list[float] | None:
    if spin_mode != SpinMode.NONCOLLINEAR:
        return None
    saxis = (parameters or {}).get("SAXIS")
    return [float(x) for x in saxis] if saxis is not None else None


class ChargeDensityRow(VolumetricGridRow):
    """A row of a charge density table: a CHGCAR (or CHG, which has no augmentation data).

    VASP stores `n(r) * V_cell` at each grid point, where `n(r)` is the density in
    1/Angstrom^3 and `V_cell` is the volume of the cell, so `n(r) = value / V_cell`, and
    the sum of the values over the grid divided by the number of grid points is the number
    of valence electrons (see https://vasp.at/wiki/CHGCAR). The values are stored as in the
    file. The PAW augmentation occupancies the file has are not stored: they are
    only needed to restart a calculation, for which the raw file is kept.

    The blocks of the file depend on the spin:
    - unpolarized: `total`, the density.
    - collinear: `total`, the density (spin up + spin down), then `magnetization`
        (spin up - spin down).
    - noncollinear: `total`, then `magnetization_1`, `magnetization_2`, `magnetization_3`,
        the magnetization density in the basis of the spin quantization axis (`saxis`).
    """

    BLOCK_COLUMNS: ClassVar[tuple[str, ...]] = (
        "total",
        "magnetization",
        "magnetization_1",
        "magnetization_2",
        "magnetization_3",
    )
    _PMG_NAMES: ClassVar[dict[str, str]] = {
        "total": "total",
        "magnetization": "diff",
        "magnetization_1": "diff_x",
        "magnetization_2": "diff_y",
        "magnetization_3": "diff_z",
    }

    total: Float32Grid | None = Field(
        None, description="The charge density times the cell volume, flattened."
    )
    magnetization: Float32Grid | None = Field(
        None,
        description="The magnetization density (spin up - spin down) times the cell "
        "volume, of a collinear calculation.",
    )
    magnetization_1: Float32Grid | None = Field(
        None,
        description="The first component of the noncollinear magnetization density.",
    )
    magnetization_2: Float32Grid | None = Field(
        None,
        description="The second component of the noncollinear magnetization density.",
    )
    magnetization_3: Float32Grid | None = Field(
        None,
        description="The third component of the noncollinear magnetization density.",
    )
    saxis: list[float] | None = Field(None, description=_SAXIS_DOC)

    @classmethod
    def from_pmg(
        cls, pmg_obj: Any, parameters: Any = None, **kwargs: Any
    ) -> ChargeDensityRow:
        """Make a row from a pymatgen Chgcar, and the parameters of its calculation."""
        columns = cls._grid_columns(pmg_obj, {v: k for k, v in cls._PMG_NAMES.items()})
        return cls(**columns, saxis=_saxis(parameters, columns["spin_mode"]), **kwargs)

    def to_pmg(self, pmg_cls: Any = Chgcar) -> Chgcar:
        """Make a pymatgen object, with the labels pymatgen gives the blocks."""
        data = self._with_noncollinear_diff(self._data_for(self._PMG_NAMES))
        return pmg_cls(self.structure, data)


class PartialChargeDensityRow(ChargeDensityRow):
    """A row of the partial charge density table: one PARCHG file.

    A PARCHG holds the part of the density that comes from the bands and k-points
    selected with the `IBAND`, `EINT`, `NBMOD` and `KPUSE` tags (see
    https://vasp.at/wiki/PARCHG), with the blocks and units of a CHGCAR, but without
    augmentation occupancies. With `LSEPB` and `LSEPK`, a file is written for each
    band and k-point, and `band_index` and `kpoint_index` are the ones in its name.
    Together with the identifier, they are the key of a row.
    """

    band_index: int | None = Field(
        None,
        description="The index of the band in the file name, PARCHG.<band>.<k-point>. "
        "Null if the file is the sum of the selected bands (it is named ALLB or has no "
        "indices).",
    )
    kpoint_index: int | None = Field(
        None,
        description="The index of the k-point in the file name. Null if the file is "
        "the sum of the selected k-points (it is named ALLK or has no indices).",
    )
    iband: list[int] | None = Field(None, description="The IBAND tag: the bands used.")
    eint: list[float] | None = Field(
        None, description="The EINT tag: the energy range of the bands used."
    )
    nbmod: int | None = Field(
        None, description="The NBMOD tag: how the bands used are selected."
    )
    kpuse: list[int] | None = Field(
        None, description="The KPUSE tag: the k-points used."
    )
    lsepb: bool | None = Field(
        None, description="The LSEPB tag: whether a file is written for each band."
    )
    lsepk: bool | None = Field(
        None, description="The LSEPK tag: whether a file is written for each k-point."
    )

    @classmethod
    def from_pmg(  # type: ignore[override]
        cls, pmg_obj: Any, parameters: Any = None, **kwargs: Any
    ) -> PartialChargeDensityRow:
        """Make a row from a pymatgen Chgcar of a PARCHG, and its calculation's parameters.

        `file_name` is needed, as the indices of the bands and k-points are in it.
        """
        parameters = parameters or {}
        band_index, kpoint_index = parchg_indices(kwargs["file_name"])
        columns = cls._grid_columns(pmg_obj, {v: k for k, v in cls._PMG_NAMES.items()})

        def _list(name: str, cast: Any) -> list | None:
            value = parameters.get(name)
            if value is None:
                return None
            return [
                cast(x) for x in (value if isinstance(value, list | tuple) else [value])
            ]

        nbmod = parameters.get("NBMOD")
        return cls(
            **columns,
            saxis=_saxis(parameters, columns["spin_mode"]),
            band_index=band_index,
            kpoint_index=kpoint_index,
            iband=_list("IBAND", int),
            eint=_list("EINT", float),
            nbmod=int(nbmod) if nbmod is not None else None,
            kpuse=_list("KPUSE", int),
            lsepb=parameters.get("LSEPB"),
            lsepk=parameters.get("LSEPK"),
            **kwargs,
        )


_ALL_PARTS = ("ALLB", "ALLK")


def parchg_indices(file_name: str) -> tuple[int | None, int | None]:
    """The band and k-point indices in the name of a PARCHG file, None for all.

    PARCHG.0003.0002 is band 3 and k-point 2. PARCHG.0003.ALLK is band 3, summed over
    the k-points, and PARCHG.ALLB.0002 is k-point 2, summed over the bands. A PARCHG
    with no indices is summed over both. Compression extensions and calculation
    suffixes are ignored.
    """
    parts = [
        part
        for part in file_name.rsplit("/", 1)[-1].split(".")[1:]
        if part.isdigit() or part in _ALL_PARTS
    ]
    if len(parts) != 2:
        return None, None
    band, kpoint = parts
    return (
        int(band) if band.isdigit() else None,
        int(kpoint) if kpoint.isdigit() else None,
    )


class AllElectronDensityRow(VolumetricGridRow):
    """A row of an all-electron density table: one of the AECCAR files.

    With `LAECHG = .TRUE.`, VASP reconstructs the all-electron charge density, which has
    the nodal features near the nuclei that the pseudo density lacks, on the fine
    grid, and writes three files (https://vasp.at/wiki/LAECHG): AECCAR0, the core density,
    and AECCAR1, the overlapping atomic densities, are written at the start of the
    run, and AECCAR2, the self-consistent valence density, at the end. In a
    relaxation, their structures can differ. The values have the units of a CHGCAR:
    `n(r) * V_cell`. Charge partitioning, e.g., a Bader analysis, uses the core
    density plus the valence density.
    """

    BLOCK_COLUMNS: ClassVar[tuple[str, ...]] = ("total", "magnetization")

    total: Float32Grid | None = Field(
        None, description="The density times the cell volume, flattened."
    )
    magnetization: Float32Grid | None = Field(
        None,
        description="The magnetization density (spin up - spin down) times the cell "
        "volume, if the file has a second block.",
    )

    @classmethod
    def from_pmg(
        cls, pmg_obj: Any, parameters: Any = None, **kwargs: Any
    ) -> AllElectronDensityRow:
        """Make a row from a pymatgen Chgcar of an AECCAR.

        `parameters` is not used, it is accepted so that every row is made the same way.
        """
        return cls(
            **cls._grid_columns(pmg_obj, {"total": "total", "diff": "magnetization"}),
            **kwargs,
        )

    def to_pmg(self, pmg_cls: Any = Chgcar) -> Chgcar:
        return pmg_cls(
            self.structure,
            self._data_for({"total": "total", "magnetization": "diff"}),
        )


class LocalPotentialRow(VolumetricGridRow):
    """A row of a local potential table: a LOCPOT (or POT, which also has augmentation data).

    The values are the potential in eV, not multiplied by the volume. What the
    potential is depends on the settings of the calculation (see `potential_kind`):
    https://vasp.at/wiki/LOCPOT, https://vasp.at/wiki/LVTOT, https://vasp.at/wiki/LVHAR.

    The blocks depend on the spin:
    - unpolarized: `potential`.
    - collinear: `spin_up` and `spin_down`, the potentials of each spin.
    - noncollinear: `potential`, the scalar potential, then `b_field_1`, `b_field_2` and
        `b_field_3`, the B-field-like potential in the basis of the spin quantization
        axis (`saxis`).
    """

    BLOCK_COLUMNS: ClassVar[tuple[str, ...]] = (
        "potential",
        "spin_up",
        "spin_down",
        "b_field_1",
        "b_field_2",
        "b_field_3",
    )

    potential: Float32Grid | None = Field(
        None, description="The scalar potential, in eV, flattened."
    )
    spin_up: Float32Grid | None = Field(
        None, description="The spin-up potential of a collinear calculation, in eV."
    )
    spin_down: Float32Grid | None = Field(
        None, description="The spin-down potential of a collinear calculation, in eV."
    )
    b_field_1: Float32Grid | None = Field(
        None,
        description="The first component of the noncollinear B-field-like potential.",
    )
    b_field_2: Float32Grid | None = Field(
        None,
        description="The second component of the noncollinear B-field-like potential.",
    )
    b_field_3: Float32Grid | None = Field(
        None,
        description="The third component of the noncollinear B-field-like potential.",
    )
    saxis: list[float] | None = Field(None, description=_SAXIS_DOC)
    lvtot: bool | None = Field(
        None,
        description="The LVTOT tag: write the total local potential, the sum of the "
        "ionic, Hartree and (semi-)local exchange-correlation potentials.",
    )
    lvhar: bool | None = Field(
        None,
        description="The LVHAR tag: write the sum of the ionic and Hartree potentials "
        "only. It sets LVTOT to false.",
    )
    wrt_potential: list[str] | None = Field(
        None,
        description="The WRT_POTENTIAL tag: the components of the potential written to "
        "vaspout.h5, one of which, `total`, is also written to the LOCPOT.",
    )
    potential_kind: Literal["total", "electrostatic"] | None = Field(
        None,
        description="What the potential in the file is, from the tags above: `total` "
        "(ionic + Hartree + exchange-correlation) or `electrostatic` (ionic + Hartree). "
        "Null if the tags do not say. Note that the exchange-correlation part only "
        "covers (semi-)local functionals, not the meta-GGA kinetic energy density "
        "potential or the nonlocal exchange of hybrids.",
    )

    @classmethod
    def from_pmg(
        cls, pmg_obj: Any, parameters: Any = None, **kwargs: Any
    ) -> LocalPotentialRow:
        """Make a row from a pymatgen Locpot (or Pot), and the parameters of its calculation."""
        parameters = parameters or {}
        columns = cls._grid_columns(
            pmg_obj,
            {
                "total": "potential",
                "spin_up": "spin_up",
                "spin_down": "spin_down",
                "diff_x": "b_field_1",
                "diff_y": "b_field_2",
                "diff_z": "b_field_3",
            },
        )
        lvtot, lvhar = parameters.get("LVTOT"), parameters.get("LVHAR")
        wrt = parameters.get("WRT_POTENTIAL")
        wrt_list = wrt.split() if isinstance(wrt, str) else wrt
        if lvhar:
            kind = "electrostatic"
        elif lvtot or (wrt_list and "total" in wrt_list):
            kind = "total"
        else:
            kind = None
        return cls(
            **columns,
            saxis=_saxis(parameters, columns["spin_mode"]),
            lvtot=lvtot,
            lvhar=lvhar,
            wrt_potential=wrt_list,
            potential_kind=kind,
            **kwargs,
        )

    def to_pmg(self, pmg_cls: Any = Locpot) -> Locpot:
        names = {
            "potential": "total",
            "spin_up": "spin_up",
            "spin_down": "spin_down",
            "b_field_1": "diff_x",
            "b_field_2": "diff_y",
            "b_field_3": "diff_z",
        }
        return pmg_cls(
            self.structure, self._with_noncollinear_diff(self._data_for(names))
        )


class ElectronLocalizationRow(VolumetricGridRow):
    """A row of the electron localization function (ELF) table: an ELFCAR.

    The ELF is dimensionless, between 0 and 1 (https://vasp.at/wiki/ELFCAR). VASP does not
    implement it for noncollinear calculations, so there are only two layouts:
    - unpolarized: `elf`.
    - collinear: `elf_up`, then `elf_down`.
    """

    BLOCK_COLUMNS: ClassVar[tuple[str, ...]] = ("elf", "elf_up", "elf_down")

    elf: Float32Grid | None = Field(
        None, description="The electron localization function, flattened."
    )
    elf_up: Float32Grid | None = Field(
        None,
        description="The ELF of the spin-up electrons, of a collinear calculation.",
    )
    elf_down: Float32Grid | None = Field(
        None,
        description="The ELF of the spin-down electrons, of a collinear calculation.",
    )

    @classmethod
    def from_pmg(
        cls, pmg_obj: Any, parameters: Any = None, **kwargs: Any
    ) -> ElectronLocalizationRow:
        """Make a row from a pymatgen Elfcar.

        `parameters` is not used, it is accepted so that every row is made the same way.
        """
        return cls(
            **cls._grid_columns(
                pmg_obj,
                {"total": "elf", "spin_up": "elf_up", "spin_down": "elf_down"},
            ),
            **kwargs,
        )

    def to_pmg(self, pmg_cls: Any = Elfcar) -> Elfcar:
        return pmg_cls(
            self.structure,
            self._data_for(
                {"elf": "total", "elf_up": "spin_up", "elf_down": "spin_down"}
            ),
        )


_ELECTRONIC_CONTEXT = {
    "ispin": ("ISPIN", int),
    "nelect": ("NELECT", float),
    "nbands": ("NBANDS", int),
    "ismear": ("ISMEAR", int),
    "sigma": ("SIGMA", float),
    "lorbit": ("LORBIT", int),
}
"""The columns that describe how the electronic structure was calculated, by the
VASP parameter they come from, and its type."""


def _electronic_context(parameters: Any) -> dict[str, Any]:
    parameters = parameters or {}
    return {
        column: kind(parameters[key])
        for column, (key, kind) in _ELECTRONIC_CONTEXT.items()
        if parameters.get(key) is not None
    }


def _electronic_spin_mode(parameters: Any, spins: Sequence[Any]) -> SpinMode:
    """The spin mode of a DOS or band structure.

    A noncollinear calculation has one set of data, as an unpolarized one does:
    pymatgen drops the magnetization components, so only the parameters tell them apart.
    """
    if (parameters or {}).get("LNONCOLLINEAR"):
        return SpinMode.NONCOLLINEAR
    return SpinMode.COLLINEAR if len(spins) == 2 else SpinMode.UNPOLARIZED


def _spin_columns(name: str, spin_mode: SpinMode, by_spin: dict[Any, Any]) -> dict:
    """The columns of a quantity: `name`, or `name_up` and `name_down` if collinear."""
    if spin_mode == SpinMode.COLLINEAR:
        return {f"{name}_up": by_spin[Spin.up], f"{name}_down": by_spin[Spin.down]}
    return {name: by_spin[Spin.up]}


def _by_spin(row: BaseModel, name: str) -> dict[Any, Any]:
    """The spin-resolved data of a row, by spin: the inverse of `_spin_columns`."""
    if (total := getattr(row, name)) is not None:
        return {Spin.up: total}
    return {
        spin: values
        for spin in Spin
        if (values := getattr(row, f"{name}_{spin.name}")) is not None
    }


class _SpinBlocks(BaseModel):
    """Checks that a row has the columns of its spin mode, and no others.

    A quantity with a spin mode of `collinear` is in the columns `<name>_up` and
    `<name>_down`. For any other mode it is in the column `<name>`.
    """

    SPIN_BLOCKS: ClassVar[tuple[str, ...]] = ()
    """The names of the quantities that have a column for each spin."""
    OPTIONAL_SPIN_BLOCKS: ClassVar[tuple[str, ...]] = ()
    """Quantities that a row may not have at all."""

    @model_validator(mode="after")
    def check_spin_columns(self) -> Self:
        expected = (
            {"_up", "_down"} if self.spin_mode == SpinMode.COLLINEAR else {""}  # type: ignore[attr-defined]
        )
        for name in self.SPIN_BLOCKS:
            present = {
                suffix
                for suffix in ("", "_up", "_down")
                if getattr(self, f"{name}{suffix}") is not None
            }
            if not present and name in self.OPTIONAL_SPIN_BLOCKS:
                continue
            if present != expected:
                raise ValueError(
                    f"A {self.spin_mode.value} row has "  # type: ignore[attr-defined]
                    f"the columns {sorted(f'{name}{s}' for s in expected)} for "
                    f"`{name}`, not {sorted(f'{name}{s}' for s in present)}."
                )
        return self


class ElectronicStructureRow(ParsedRowHeader, _SpinBlocks, _HasStructure):
    """The columns of the rows of a DOS and of a band structure table.

    The structure is stored as its lattice, species and fractional coordinates. It is
    the final structure of the calculation, the one the DOS and the band structure
    were calculated for. The settings come from the effective `parameters` of the
    vasprun.xml, which include the defaults.

    Rows with the projections of the same calculation are in their own tables, see
    `DosProjectionsRow` and `BandStructureProjectionsRow`.
    """

    spin_mode: SpinMode = Field(
        description="How the spin is represented. `collinear` has the columns of both "
        "spins (`_up` and `_down`). `unpolarized` and `noncollinear` have one set of "
        "columns: pymatgen does not read the magnetization components of a noncollinear "
        "calculation, so it is not stored."
    )
    lattice: list[list[float]] = Field(
        description="The lattice vectors a, b, c, as rows, in Angstrom."
    )
    species: list[str] = Field(
        description="The element of each site, in the order of the structure."
    )
    frac_coords: list[list[float]] = Field(
        description="The fractional coordinates of each site."
    )
    ispin: int | None = Field(None, description="The ISPIN tag.")
    nelect: float | None = Field(
        None, description="The number of electrons (NELECT) of the calculation."
    )
    nbands: int | None = Field(
        None,
        description="The number of bands (NBANDS). For a noncollinear calculation "
        "these are spinors.",
    )
    ismear: int | None = Field(
        None,
        description="The ISMEAR tag, the smearing, or -5 for the tetrahedron method.",
    )
    sigma: float | None = Field(
        None, description="The SIGMA tag, the smearing width in eV."
    )
    lorbit: int | None = Field(
        None,
        description="The LORBIT tag, which decides whether projections are written "
        "and for which orbitals.",
    )


def _same_length(row: BaseModel, names: Sequence[str], size: int, what: str) -> None:
    for name in names:
        if (values := getattr(row, name, None)) is not None and len(values) != size:
            raise ValueError(
                f"`{name}` has {len(values)} values, but {what} is {size}."
            )


class DosRow(ElectronicStructureRow):
    """A row of the total density of states table: the DOS of one calculation.

    `density` is VASP's total DOS in states / eV for the unit cell, on the energies
    `energies`, which are absolute (the Fermi level is `efermi`). For an unpolarized
    calculation, it counts both spins. `integrated` is VASP's integrated DOS, the number
    of electrons below each energy, obtained with the same smearing or tetrahedron method.
    At the Fermi level it is NELECT, for a calculation which has no states below the
    energy window. A collinear calculation has `density_up`, `density_down`,
    `integrated_up` and `integrated_down`.

    The energies and densities are float32, which is exact for the energies, which
    VASP writes with four decimals.
    """

    SPIN_BLOCKS: ClassVar[tuple[str, ...]] = ("density", "integrated")
    OPTIONAL_SPIN_BLOCKS: ClassVar[tuple[str, ...]] = ("integrated",)

    efermi: float = Field(description="The Fermi energy, in eV.")
    energies: Float32List = Field(
        description="The energies of the DOS, in eV, ascending."
    )
    density: Float32List | None = Field(
        None, description="The total DOS, in states / eV, counting every spin."
    )
    density_up: Float32List | None = Field(None, description="The spin-up DOS.")
    density_down: Float32List | None = Field(None, description="The spin-down DOS.")
    integrated: Float32List | None = Field(
        None, description="The integrated DOS, in electrons, counting every spin."
    )
    integrated_up: Float32List | None = Field(
        None, description="The integrated spin-up DOS."
    )
    integrated_down: Float32List | None = Field(
        None, description="The integrated spin-down DOS."
    )

    _projections: Any = PrivateAttr(None)

    @model_validator(mode="after")
    def check_lengths(self) -> Self:
        names = [
            f"{name}{suffix}"
            for name in self.SPIN_BLOCKS
            for suffix in ("", "_up", "_down")
        ]
        _same_length(self, names, len(self.energies), "the number of energies")
        return self

    @classmethod
    def from_pmg(
        cls, dos: Any, idos: Any = None, parameters: Any = None, **kwargs: Any
    ) -> DosRow:
        """Make a row from a pymatgen CompleteDos, and the settings of its calculation.

        The row of the projections is made along with it, which `split_dos_row` takes.

        Parameters
        -----------
        dos : CompleteDos
            The DOS, which must have a structure.
        idos : Dos or None
            The integrated DOS of the vasprun.xml, `Vasprun.idos`, if wanted.
        parameters : dict or None
            The parameters of the calculation, `Vasprun.parameters`.
        kwargs
            The columns of the header.
        """
        structure = getattr(dos, "structure", None)
        if structure is None:
            raise ValueError("The DOS needs a structure, use a CompleteDos.")
        spins = [spin for spin in Spin if spin in dos.densities]
        spin_mode = _electronic_spin_mode(parameters, spins)

        def f32(by_spin: dict[Any, Any]) -> dict[Any, Any]:
            return {
                spin: np.asarray(v, dtype=np.float32) for spin, v in by_spin.items()
            }

        columns = {
            "spin_mode": spin_mode,
            **_structure_columns(structure),
            **_electronic_context(parameters),
            "efermi": float(dos.efermi),
            "energies": np.asarray(dos.energies, dtype=np.float32),
            **_spin_columns("density", spin_mode, f32(dos.densities)),
        }
        if idos is not None:
            columns.update(_spin_columns("integrated", spin_mode, f32(idos.densities)))
        row = cls(**columns, **kwargs)
        row._projections = DosProjectionsRow.from_pmg(
            dos, spin_mode=spin_mode, **kwargs
        )
        return row

    def to_pmg(self, projections: DosProjectionsRow | None = None) -> Any:
        """Make a pymatgen object: a Dos, or a CompleteDos if there are projections.

        Parameters
        -----------
        projections : DosProjectionsRow or None
            The row of the projected DOS table with the same identifier, if wanted.
        """
        dos = Dos(
            self.efermi,
            np.asarray(self.energies, dtype=float),
            {
                spin: np.asarray(v, dtype=float)
                for spin, v in _by_spin(self, "density").items()
            },
        )
        if projections is None:
            return dos
        if projections.identifier != self.identifier:
            raise ValueError(
                f"The projections of {projections.identifier} do not belong to the "
                f"DOS of {self.identifier}."
            )
        return CompleteDos(
            self.structure, dos, projections.to_pdos(self.structure, len(self.energies))
        )

    def take_projections(self) -> DosProjectionsRow | None:
        """Take the row of the projections made along with this one, which it then does not have."""
        projections, self._projections = self._projections, None
        return projections


class DosProjectionsRow(ParsedRowHeader, _SpinBlocks):
    """A row of the projected density of states table.

    `density` is the DOS projected onto each orbital of each site, as written by VASP
    (within the spheres of the PAW method, so the sum over the orbitals is not the
    total DOS). It is flattened in C order from an array indexed `[site, orbital, energy]`:
    rebuild it with `np.reshape(density, shape)`. The sites are those of the structure of
    the row of the total DOS table with the same identifier, in its order, and the
    energies are its `energies`.
    """

    SPIN_BLOCKS: ClassVar[tuple[str, ...]] = ("density",)

    spin_mode: SpinMode = Field(
        description="How the spin is represented, as in the total DOS table."
    )
    orbitals: list[str] = Field(
        description="The orbital of each index of the second axis, e.g., s, py, pz, px, "
        "dxy, ... for LORBIT = 11, or s, p, d for LORBIT = 10."
    )
    shape: list[int] = Field(
        description="The shape of the arrays: the number of sites, orbitals and energies."
    )
    density: Float32Grid | None = Field(
        None, description="The projected DOS, which counts every spin."
    )
    density_up: Float32Grid | None = Field(
        None, description="The spin-up projected DOS."
    )
    density_down: Float32Grid | None = Field(
        None, description="The spin-down projected DOS."
    )

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        if len(self.shape) != 3 or self.shape[1] != len(self.orbitals):
            raise ValueError(
                f"The shape {self.shape} is not (sites, {len(self.orbitals)} orbitals, energies)."
            )
        size = int(np.prod(self.shape))
        _same_length(
            self,
            ["density", "density_up", "density_down"],
            size,
            f"the size of the shape {self.shape}",
        )
        return self

    @classmethod
    def from_pmg(
        cls, dos: Any, spin_mode: SpinMode, **kwargs: Any
    ) -> DosProjectionsRow | None:
        """Make a row from the projections of a pymatgen CompleteDos.

        Returns None if the DOS has none. `kwargs` are the columns of the header.
        """
        if not dos.pdos:
            return None
        structure = dos.structure
        indices = _get_site_indices(dos.pdos, structure)
        if sorted(indices) != list(range(len(structure))):
            raise ValueError("The projected DOS does not have every site once.")
        orbitals = [[orbital.name for orbital in orbs] for orbs in dos.pdos.values()]
        if any(names != orbitals[0] for names in orbitals):
            raise ValueError("The sites of the projected DOS have different orbitals.")
        num_energies = len(dos.energies)
        spins = [spin for spin in Spin if spin in dos.densities]
        grids = {
            spin: np.empty((len(structure), len(orbitals[0]), num_energies), np.float32)
            for spin in spins
        }
        for index, orbs in zip(indices, dos.pdos.values()):
            for j, spin_dos in enumerate(orbs.values()):
                for spin in spins:
                    grids[spin][index, j] = spin_dos[spin]
        return cls(
            spin_mode=spin_mode,
            orbitals=orbitals[0],
            shape=list(grids[spins[0]].shape),
            **_spin_columns(
                "density", spin_mode, {s: g.ravel(order="C") for s, g in grids.items()}
            ),
            **kwargs,
        )

    def to_pdos(self, structure: Structure, num_energies: int) -> dict[Any, Any]:
        """The projections as pymatgen has them: `{site: {orbital: {spin: density}}}`."""
        if self.shape[0] != len(structure) or self.shape[2] != num_energies:
            raise ValueError(
                f"The projections have the shape {self.shape}, which does not fit a "
                f"structure of {len(structure)} sites and {num_energies} energies."
            )
        # The names of LORBIT = 10 are those of the types of orbital, which have p
        orbital_cls = OrbitalType if "p" in self.orbitals else Orbital
        grids = {
            spin: np.asarray(v, dtype=float).reshape(self.shape, order="C")
            for spin, v in _by_spin(self, "density").items()
        }
        return {
            structure[i]: {
                orbital_cls[name]: {spin: grid[i, j] for spin, grid in grids.items()}
                for j, name in enumerate(self.orbitals)
            }
            for i in range(len(structure))
        }


def _projection_orbitals(count: int) -> list[str]:
    """The orbitals of the projections of a band structure, by how many there are.

    pymatgen does not keep their names. VASP writes the 9 (s, p, d) or 16 (also f)
    orbitals of LORBIT = 11 and the 3 or 4 of LORBIT = 10, in the order of pymatgen.
    """
    if count in (9, 16):
        return [Orbital(i).name for i in range(count)]
    if count in (3, 4):
        return [OrbitalType(i).name for i in range(count)]
    raise ValueError(f"The projections have {count} orbitals, which are not known.")


class BandStructureRow(ElectronicStructureRow):
    """A row of the band structure table.

    The bands are `bands`, in eV, flattened in C order from an array indexed
    `[band, k-point]`: rebuild it with `np.reshape(bands, shape)`. The k-points are
    `qpoints`, in direct coordinates of the reciprocal lattice. A collinear
    calculation has `bands_up` and `bands_down`.

    A band structure along a path of k-points has `kpoint_labels`, and no weights.
    One on a uniform mesh of k-points has `kpoint_weights` (those of the irreducible
    k-points, which sum to 1) and no labels.
    """

    SPIN_BLOCKS: ClassVar[tuple[str, ...]] = ("bands",)

    path_convention: BSPathType = Field(
        description="The high symmetry path the band structure follows: `uniform` for "
        "a mesh of k-points, which has no path, and `unknown` for a path that could "
        "not be identified."
    )
    kpath: list[str] | None = Field(
        None, description="The labels of the path in order, if it was identified."
    )
    qpoints: list[list[float]] = Field(
        description="The k-points, in direct coordinates of the reciprocal lattice."
    )
    kpoint_labels: list[str | None] | None = Field(
        None,
        description="The label of each k-point, null for the k-points that have none. "
        "Where a path has a break, the end of a segment and the start of the next both "
        "have a label. Null for a band structure with no labels at all.",
    )
    kpoint_weights: list[float] | None = Field(
        None,
        description="The weight of each k-point, for a band structure on a mesh of "
        "k-points. Null for one along a path, whose k-points have no weight.",
    )
    reciprocal_lattice: list[list[float]] = Field(
        description="The reciprocal lattice vectors, as rows, in 1/Angstrom, including the "
        "factor 2 pi, which is the convention of pymatgen."
    )
    efermi: float = Field(
        description="The Fermi energy, in eV, which the band structure is relative to. "
        "For a path, pymatgen chooses it from the bands."
    )
    band_gap: float | None = Field(
        None, description="The band gap, in eV, 0 for a metal."
    )
    is_direct: bool | None = Field(
        None, description="Whether the band gap is direct, for a non-zero gap."
    )
    shape: list[int] = Field(
        description="The shape of the bands: the number of bands and k-points."
    )
    bands: Float32Grid | None = Field(
        None, description="The eigenvalues, in eV, of every spin."
    )
    bands_up: Float32Grid | None = Field(None, description="The spin-up eigenvalues.")
    bands_down: Float32Grid | None = Field(
        None, description="The spin-down eigenvalues."
    )

    _projections: Any = PrivateAttr(None)

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        num_kpoints = len(self.qpoints)
        if len(self.shape) != 2 or self.shape[1] != num_kpoints:
            raise ValueError(
                f"The shape {self.shape} is not (bands, {num_kpoints} k-points)."
            )
        _same_length(
            self,
            ["bands", "bands_up", "bands_down"],
            int(np.prod(self.shape)),
            f"the size of the shape {self.shape}",
        )
        _same_length(
            self,
            ["kpoint_labels", "kpoint_weights"],
            num_kpoints,
            "the number of k-points",
        )
        return self

    @classmethod
    def from_pmg(
        cls,
        band_structure: Any,
        parameters: Any = None,
        kpoint_weights: Sequence[float] | None = None,
        path_convention: BSPathType | None = None,
        **kwargs: Any,
    ) -> BandStructureRow:
        """Make a row from a pymatgen band structure, and the settings of its calculation.

        The row of the projections is made along with it, which `split_band_structure_row`
        takes.

        Parameters
        -----------
        band_structure : BandStructure
            Which must have a structure, as that of a vasprun.xml does.
        parameters : dict or None
            The parameters of the calculation, `Vasprun.parameters`.
        kpoint_weights : sequence of float or None
            The weight of each k-point of a band structure on a mesh.
        path_convention : BSPathType or None
            The path the band structure follows. It is identified from the labels and
            the structure if not given, which is not wanted for a mesh of k-points
            (`BSPathType.uniform`), which has no path.
        kwargs
            The columns of the header.
        """
        structure = band_structure.structure
        if structure is None:
            raise ValueError("The band structure needs a structure.")
        qpoints = [kpt.frac_coords.tolist() for kpt in band_structure.kpoints]
        labels = {
            label: kpt.frac_coords.tolist()
            for label, kpt in (band_structure.labels_dict or {}).items()
        }
        kpath = None
        if path_convention is None:
            path_convention, kpath, labels = infer_path(structure, qpoints, labels)

        spins = [spin for spin in Spin if spin in band_structure.bands]
        spin_mode = _electronic_spin_mode(parameters, spins)
        bands = {
            spin: np.asarray(v, dtype=np.float32)
            for spin, v in band_structure.bands.items()
        }
        shape = bands[spins[0]].shape
        if any(b.shape != shape for b in bands.values()):
            raise ValueError("The spins of the band structure have different shapes.")
        gap = band_structure.get_band_gap()
        row = cls(
            spin_mode=spin_mode,
            **_structure_columns(structure),
            **_electronic_context(parameters),
            path_convention=path_convention,
            kpath=kpath,
            qpoints=qpoints,
            kpoint_labels=_label_kpoints(qpoints, labels),
            kpoint_weights=(
                None if kpoint_weights is None else [float(w) for w in kpoint_weights]
            ),
            reciprocal_lattice=band_structure.lattice_rec.matrix.tolist(),
            efermi=float(band_structure.efermi),
            band_gap=gap["energy"],
            is_direct=gap["direct"],
            shape=list(shape),
            **_spin_columns(
                "bands", spin_mode, {s: b.ravel(order="C") for s, b in bands.items()}
            ),
            **kwargs,
        )
        if band_structure.projections:
            row._projections = BandStructureProjectionsRow.from_pmg(
                band_structure.projections,
                spin_mode=spin_mode,
                path_convention=path_convention,
                **kwargs,
            )
        return row

    def to_pmg(
        self,
        projections: BandStructureProjectionsRow | None = None,
        pmg_cls: Any = None,
    ) -> Any:
        """Make a pymatgen band structure.

        Parameters
        -----------
        projections : BandStructureProjectionsRow or None
            The row of the projected band structure table with the same identifier,
            if wanted.
        pmg_cls : class or None
            A `BandStructureSymmLine` if the row has labels, and a `BandStructure`
            if not, unless it is given.
        """
        if projections is not None:
            if projections.identifier != self.identifier:
                raise ValueError(
                    f"The projections of {projections.identifier} do not belong to the "
                    f"band structure of {self.identifier}."
                )
            if projections.shape[:2] != self.shape or projections.shape[3] != len(
                self.species
            ):
                raise ValueError(
                    f"The projections have the shape {projections.shape}, which does "
                    f"not fit bands of shape {self.shape} and {len(self.species)} sites."
                )
        labels = {
            label: qpoint
            for label, qpoint in zip(self.kpoint_labels or [], self.qpoints)
            if label is not None
        }
        if pmg_cls is None:
            pmg_cls = BandStructureSymmLine if labels else PmgBandStructure
        return pmg_cls(
            np.asarray(self.qpoints),
            {
                spin: np.asarray(v, dtype=float).reshape(self.shape, order="C")
                for spin, v in _by_spin(self, "bands").items()
            },
            Lattice(self.reciprocal_lattice),
            self.efermi,
            labels_dict=labels,
            coords_are_cartesian=False,
            structure=self.structure,
            projections=projections.to_pmg_like() if projections else None,
        )

    def take_projections(self) -> BandStructureProjectionsRow | None:
        """Take the row of the projections made along with this one, which it then does not have."""
        projections, self._projections = self._projections, None
        return projections


def _label_kpoints(
    qpoints: Sequence[Sequence[float]], labels: dict[str, Sequence[float]]
) -> list[str | None] | None:
    """The label of each k-point, in the way pymatgen gives them: by its coordinates.

    A k-point on two labels has the last one. None if no k-point has a label.
    """
    if not labels or not len(qpoints):
        return None
    names = list(labels)
    distances = np.linalg.norm(
        np.asarray(qpoints)[:, None, :] - np.asarray([labels[n] for n in names])[None],
        axis=-1,
    )
    found = [
        next((names[j] for j in np.flatnonzero(row < 1e-4)[::-1]), None)
        for row in distances
    ]
    return found if any(label is not None for label in found) else None


class BandStructureProjectionsRow(ParsedRowHeader, _SpinBlocks):
    """A row of the projected band structure table.

    `weights` are the projections of the bands onto the orbitals of each site, as written
    by VASP: the weight of an orbital in a band at a k-point. They are flattened in
    C order from an array indexed `[band, k-point, orbital, site]`, so that the first
    two axes are those of the bands of the band structure table: rebuild it with
    `np.reshape(weights, shape)`. The sites are those of the structure of the row of
    the band structure table with the same identifier, in its order.
    """

    SPIN_BLOCKS: ClassVar[tuple[str, ...]] = ("weights",)

    spin_mode: SpinMode = Field(
        description="How the spin is represented, as in the band structure table."
    )
    path_convention: BSPathType = Field(
        description="High symmetry path convention of the band structure. "
        "A copy of the column of the band structure table, which partitions both tables."
    )
    orbitals: list[str] = Field(
        description="The orbital of each index of the third axis, e.g., s, py, pz, px, "
        "dxy, ... for LORBIT = 11, or s, p, d for LORBIT = 10."
    )
    shape: list[int] = Field(
        description="The shape of the weights: the number of bands, k-points, orbitals "
        "and sites."
    )
    weights: Float32Grid | None = Field(
        None, description="The projections, for every spin."
    )
    weights_up: Float32Grid | None = Field(None, description="The spin-up projections.")
    weights_down: Float32Grid | None = Field(
        None, description="The spin-down projections."
    )

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        if len(self.shape) != 4 or self.shape[2] != len(self.orbitals):
            raise ValueError(
                f"The shape {self.shape} is not (bands, k-points, {len(self.orbitals)} "
                "orbitals, sites)."
            )
        _same_length(
            self,
            ["weights", "weights_up", "weights_down"],
            int(np.prod(self.shape)),
            f"the size of the shape {self.shape}",
        )
        return self

    @classmethod
    def from_pmg(
        cls,
        projections: dict[Any, Any],
        spin_mode: SpinMode,
        path_convention: BSPathType,
        **kwargs: Any,
    ) -> BandStructureProjectionsRow:
        """Make a row from the projections of a pymatgen band structure, `{spin: array}`.

        `kwargs` are the columns of the header.
        """
        grids = {
            spin: np.asarray(v, dtype=np.float32) for spin, v in projections.items()
        }
        shape = next(iter(grids.values())).shape
        if any(g.shape != shape for g in grids.values()):
            raise ValueError("The projections of the spins have different shapes.")
        return cls(
            spin_mode=spin_mode,
            path_convention=path_convention,
            orbitals=_projection_orbitals(shape[2]),
            shape=list(shape),
            **_spin_columns(
                "weights", spin_mode, {s: g.ravel(order="C") for s, g in grids.items()}
            ),
            **kwargs,
        )

    def to_pmg_like(self) -> dict[Any, Any]:
        """The projections as pymatgen has them: `{spin: array}`."""
        return {
            spin: np.asarray(v, dtype=float).reshape(self.shape, order="C")
            for spin, v in _by_spin(self, "weights").items()
        }


def split_dos_row(row: DosRow) -> tuple[DosRow, DosProjectionsRow | None]:
    """Take the projections of a DOS, which are in their own table.

    Returns
    -----------
    DosRow
        The row (the same object as the input), which no longer has the projections.
    DosProjectionsRow or None
        None if the DOS has no projections.
    """
    return row, row.take_projections()


def split_band_structure_row(
    row: BandStructureRow,
) -> tuple[BandStructureRow, BandStructureProjectionsRow | None]:
    """Take the projections of a band structure, which are in their own table.

    Returns
    -----------
    BandStructureRow
        The row (the same object as the input), which no longer has the projections.
    BandStructureProjectionsRow or None
        None if the band structure has no projections.
    """
    return row, row.take_projections()


class ValidationRow(ParsedRowHeader):
    """A row of the validation table, which has the results of validating a task."""

    valid: bool = Field(description="Whether the calculation passed validation.")
    reasons: list[str] = Field(
        [], description="The reasons the calculation failed validation, if any."
    )
    warnings: list[str] = Field(
        [], description="Warnings raised during validation, if any."
    )


# The convergence data is computed by RelaxTrajectory, as properties, and is stored as
# columns of the trajectory table by the row. That the row's fields have the names of
# those properties is intended, and pydantic warns about it. Only that is silenced.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r'Field name "has_full_output" in "TrajectoryRow" shadows an attribute',
        category=UserWarning,
    )

    class TrajectoryRow(RelaxTrajectory):
        """A row of the trajectory table: a trajectory with its convergence data.

        The convergence data of a trajectory is computed from it, and computed
        properties are not columns of a table, so they are stored here. They are
        columns of the trajectories already in production, which are partitioned
        by run type.
        """

        has_full_output: bool = Field(
            description="Whether the trajectory has all structures and SCF convergence data."
        )
        energy_convergence: list[float] | None = Field(
            None, description="Convergence of the energy, see `convergence_data`."
        )
        e_fr_energy_convergence: list[float] | None = Field(
            None, description="Convergence of the free energy, see `convergence_data`."
        )
        e_wo_entrp_convergence: list[float] | None = Field(
            None,
            description="Convergence of the energy without entropy, see `convergence_data`.",
        )
        forces_convergence: list[float] | None = Field(
            None, description="Convergence of the forces, see `convergence_data`."
        )

        @classmethod
        def from_trajectory(cls, trajectory: RelaxTrajectory) -> TrajectoryRow:
            """Make a row from a trajectory, computing its convergence data."""
            values = {
                name: getattr(trajectory, name) for name in RelaxTrajectory.model_fields
            }
            convergence = trajectory.convergence_data
            return cls(
                **values,
                has_full_output=trajectory.has_full_output,
                **{
                    f"{name}_convergence": convergence.get(name)
                    for name in ("energy", "e_fr_energy", "e_wo_entrp", "forces")
                },
            )


class ParseOutcome(ValueEnum):
    """What came of parsing a calculation."""

    PARSED = "parsed"
    SKIPPED_FAILED = "skipped_failed"
    SKIPPED_UNRECOGNIZED = "skipped_unrecognized"
    ERROR = "error"


class ManifestRow(BaseModel):
    """A row of the manifest table, which records the parsing of every calculation.

    A calculation gets a row whatever came of parsing it, even if it
    could not be read at all, so that nothing disappears silently. It can also
    be used to find out which calculations have been parsed already, by
    their `dir_name` and `calc_suffix`.

    The manifest does not have the header of the other tables, because the
    properties of a calculation which could not be read are not known.
    """

    identifier: TaskIdentifierType = Field(
        description="The identifier assigned to the calculation."
    )
    dir_name: str = Field(
        description="The directory the calculation was parsed from. Together with "
        "the calc_suffix it identifies the calculation."
    )
    calc_suffix: str = Field(
        description="The suffix of the calculation in the directory, or standard."
    )
    completed_at: Annotated[datetime | None, BeforeValidator(_optional_datetime)] = (
        Field(None, description="When the calculation was completed, if known.")
    )
    parsed_at: datetime = Field(
        default_factory=utcnow, description="When the calculation was parsed."
    )
    outcome: ParseOutcome = Field(description="What came of parsing the calculation.")
    run_type: RunType | None = Field(
        None, description="The functional used in the calculation, if known."
    )
    task_type: TaskType | None = Field(
        None, description="The type of calculation, if known."
    )
    tables: list[str] = Field(
        [], description="The tables which received a row for this calculation."
    )
    errors: list[str] = Field(
        [], description="The problems which occurred while parsing the calculation."
    )


@dataclass(frozen=True)
class TableSpec:
    """The row model and physical layout of a table.

    Attributes
    -----------
    name : str
        The name of the table.
    row_model : type[BaseModel]
        The model of a row. The table schema is `pa.schema(arrowize(row_model))`.
    partition_by : tuple of str
        The columns the table is partitioned on, in order, e.g.,
        (year, month, day, run_type) gives a layout like `2026/10/28/GGA/`.
        Empty if the table is not partitioned.
    zorder_by : tuple of str
        The columns the table is sorted / Z-ordered on, within partitions.
    """

    name: str
    row_model: type[BaseModel]
    partition_by: tuple[str, ...] = ()
    zorder_by: tuple[str, ...] = ("identifier",)
    column_order: tuple[str, ...] | None = None

    @property
    def columns(self) -> set[str]:
        """The top-level columns of the table."""
        return {
            name
            for name, field in self.row_model.model_fields.items()
            if not field.exclude
        }

    def _leaf_columns(self) -> list[tuple[str, Any]]:
        """The leaves of the schema by their path in a Parquet file, and their Arrow type.

        Parquet names the elements of lists `element`, whatever their Arrow name
        is. A writer ignores a path which is not in the file, so a path with another name
        does nothing, without an error.
        """
        import pyarrow as pa

        from emmet.core.arrow import arrowize

        schema = pa.schema(arrowize(self.row_model))
        leaves: list[tuple[str, Any]] = []

        def _walk(dtype: Any, path: str) -> None:
            if pa.types.is_list(dtype) or pa.types.is_large_list(dtype):
                _walk(dtype.value_field.type, f"{path}.list.element")
            elif pa.types.is_struct(dtype):
                for child in dtype:
                    _walk(child.type, f"{path}.{child.name}")
            elif pa.types.is_map(dtype):
                _walk(dtype.key_type, f"{path}.key_value.key")
                _walk(dtype.item_type, f"{path}.key_value.value")
            else:
                leaves.append((path, dtype))

        for name in self.ordered_columns:
            if name in schema.names:
                _walk(schema.field(name).type, name)
        return leaves

    @property
    def byte_stream_split_columns(self) -> list[str]:
        """The float32 leaves of the schema, by their path in a Parquet file.

        Floating point numbers compress better when written with the BYTE_STREAM_SPLIT
        encoding than with the default one (24% smaller for a charge density).
        Requires pyarrow.
        """
        import pyarrow as pa

        return [
            path for path, dtype in self._leaf_columns() if pa.types.is_float32(dtype)
        ]

    @property
    def parquet_options(self) -> dict[str, Any]:
        """Keyword arguments for a pyarrow Parquet writer that encode the columns well.

        BYTE_STREAM_SPLIT is used for the float32 columns, which needs dictionary encoding
        to be off for them: with both, the dictionary is used and BYTE_STREAM_SPLIT is
        silently ignored. A dictionary is no use to floating point numbers of any width,
        which seldom repeat: it made a list of float64 energies 28% larger. It is used
        for the rest. Requires pyarrow.
        """
        import pyarrow as pa

        leaves = self._leaf_columns()
        return {
            "use_byte_stream_split": [
                path for path, dtype in leaves if pa.types.is_float32(dtype)
            ],
            "use_dictionary": [
                path for path, dtype in leaves if not pa.types.is_floating(dtype)
            ],
        }

    @property
    def ordered_columns(self) -> list[str]:
        """The columns of the table, in the order they are stored in.

        This is `column_order` if there is one, and otherwise the order
        of the fields of the row model.
        """
        if self.column_order is not None:
            return list(self.column_order)
        return [
            name
            for name, field in self.row_model.model_fields.items()
            if not field.exclude
        ]


_VOLUMETRIC_PARTITION = ("year", "month", "day", "run_type")

# the order of the columns of the trajectories in production: the columns they are
# found by first, then the rest alphabetically
_TRAJECTORY_PRIORITY = ("has_full_output", "identifier", "run_type", "task_type")
_TRAJECTORY_COLUMNS = (
    *_TRAJECTORY_PRIORITY,
    *sorted(
        name
        for name, field in TrajectoryRow.model_fields.items()
        if name not in _TRAJECTORY_PRIORITY and not field.exclude
    ),
)

_VOLUMETRIC_TABLE_MODELS: dict[str, type[VolumetricGridRow]] = {
    "charge-density": ChargeDensityRow,
    "partial-charge-density": PartialChargeDensityRow,
    "core-density": AllElectronDensityRow,
    "atomic-density": AllElectronDensityRow,
    "valence-density": AllElectronDensityRow,
    "local-potential": LocalPotentialRow,
    "electron-localization": ElectronLocalizationRow,
    "charge-density-chg": ChargeDensityRow,
    "local-potential-pot": LocalPotentialRow,
}

VOLUMETRIC_FILE_TABLES: dict[str, str] = {
    "CHGCAR": "charge-density",
    "PARCHG": "partial-charge-density",
    "AECCAR0": "core-density",
    "AECCAR1": "atomic-density",
    "AECCAR2": "valence-density",
    "LOCPOT": "local-potential",
    "ELFCAR": "electron-localization",
    "CHG": "charge-density-chg",
    "POT": "local-potential-pot",
}
"""The table that each type of volumetric file is parsed into."""

VOLUMETRIC_FILE_MODELS: dict[str, type[VolumetricGridRow]] = {
    file_type: _VOLUMETRIC_TABLE_MODELS[table]
    for file_type, table in VOLUMETRIC_FILE_TABLES.items()
}

PARSED_TABLES: dict[str, TableSpec] = {
    "total-dos": TableSpec("total-dos", DosRow, partition_by=("run_type",)),
    "projected-dos": TableSpec(
        "projected-dos", DosProjectionsRow, partition_by=("run_type",)
    ),
    "bandstructures": TableSpec(
        "bandstructures", BandStructureRow, partition_by=("run_type", "path_convention")
    ),
    "projected-bandstructures": TableSpec(
        "projected-bandstructures",
        BandStructureProjectionsRow,
        partition_by=("run_type", "path_convention"),
    ),
    "validation": TableSpec("validation", ValidationRow),
    "manifest": TableSpec("manifest", ManifestRow),
    "tasks": TableSpec("tasks", CoreTaskDoc, zorder_by=("task_id",)),
    "trajectories": TableSpec(
        "trajectories",
        TrajectoryRow,
        partition_by=("run_type",),
        column_order=_TRAJECTORY_COLUMNS,
    ),
    **{
        name: TableSpec(name, row_model, partition_by=_VOLUMETRIC_PARTITION)
        for name, row_model in _VOLUMETRIC_TABLE_MODELS.items()
    },
}
"""The tables of the parsed tier of large objects, by name.

The names of the DOS and band structure tables, and the order of their
partitions, are those of the tables already in production.

The volumetric files are in tables of the kind of data they hold, each with its own
model (`ChargeDensityRow`, `PartialChargeDensityRow`, `AllElectronDensityRow`,
`LocalPotentialRow`, `ElectronLocalizationRow`), because the blocks of a file mean different
things and have different units in each. See `VOLUMETRIC_FILE_TABLES`.

The tasks table is not partitioned, and the trajectories table is partitioned
by run_type.
"""


def volumetric_table_name(file_name: str) -> str | None:
    """Get the name of the table a volumetric file belongs in.

    Parameters
    -----------
    file_name : str
        The name of a file, e.g., "CHGCAR.relax1.gz".

    Returns
    -----------
    str or None
        The name of the table in `PARSED_TABLES`, or None if the file is
        not a volumetric file.
    """
    file_type = volumetric_file_type(file_name)
    return VOLUMETRIC_FILE_TABLES.get(file_type) if file_type else None
