"""Define the row models of the parsed-tier tables of large VASP objects.

Each model here describes one row of a table: an emmet-core model of a
VASP object (e.g., `ElectronicDos`), plus a header of top-level columns used
to partition, sort, and filter the table without joining on other tables.

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
`BandStructureProjectionsRow`. Use `dos_from_rows` / `band_structure_from_rows`
to put them back together.

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

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from emmet.core.band_theory import (
    BSPathType,
    ElectronicBS,
    ElectronicDos,
    ProjectedBS,
    ProjectedDos,
)
from emmet.core.tasks import CoreTaskDoc
from emmet.core.trajectory import RelaxTrajectory
from emmet.core.types.enums import ValueEnum
from emmet.core.types.typing import TaskIdentifierType
from emmet.core.utils import convert_datetime, utcnow
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.io.pymatgen import Chgcar, Elfcar, Locpot, Structure
from emmet.core.types.arrow_annotations import Float32Grid
from emmet.core.vasp.models import volumetric_file_type

if TYPE_CHECKING:
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


class DosRow(ParsedRowHeader, ElectronicDos):
    """A row of the total density of states table.

    The projections are not a column of the table. They are kept on the
    row for the convenience of building the row of the projections table from it.
    """

    projected_densities: ProjectedDos | None = Field(
        None,
        exclude=True,
        description="The orbital- and site-projected DOS. Not stored in this "
        "table, see DosProjectionsRow.",
    )


class DosProjectionsRow(ParsedRowHeader, ProjectedDos):
    """A row of the projected density of states table."""


class BandStructureRow(ParsedRowHeader, ElectronicBS):
    """A row of the band structure table.

    The projections are not a column of the table. They are kept on the
    row for the convenience of building the row of the projections table from it.
    """

    projections: ProjectedBS | None = Field(
        None,
        exclude=True,
        description="The site- and spin-orbital-projected band structure. Not "
        "stored in this table, see BandStructureProjectionsRow.",
    )


class BandStructureProjectionsRow(ParsedRowHeader, ProjectedBS):
    """A row of the projected band structure table."""

    path_convention: BSPathType = Field(
        description="High symmetry path convention of the band structure. "
        "A copy of the column of the band structure table, which partitions both tables."
    )


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


def _flat(grid: Any) -> Any:
    """Flatten a grid indexed by `[ix, iy, iz]` in C order, so that z varies fastest."""
    return np.asarray(grid).flatten(order="C")


class VolumetricGridRow(ParsedRowHeader):
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

    @property
    def structure(self) -> Structure:
        """The structure of the file, as a pymatgen object."""
        return Structure(self.lattice, self.species, self.frac_coords)

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


def _assemble_row(
    row_cls: type[BaseModel], header: ParsedRowHeader, part: BaseModel, **extra: Any
) -> Any:
    """Make a row from an already validated header and part of another model.

    The values are not validated again, so their (potentially very large)
    arrays are shared with `part`, not copied.
    """
    values = {name: getattr(header, name) for name in ParsedRowHeader.model_fields}
    values.update({name: getattr(part, name) for name in type(part).model_fields})
    values.update(extra)
    return row_cls.model_construct(**values)


def split_dos_row(row: DosRow) -> tuple[DosRow, DosProjectionsRow | None]:
    """Split the projections of a DOS into their own row.

    The projections are removed from the DOS row so they are not held twice.

    Returns
    -----------
    DosRow
        The row (the same object as the input) with no projections.
    DosProjectionsRow or None
        None if the DOS has no projections.
    """
    projections = row.projected_densities
    row.projected_densities = None
    if projections is None:
        return row, None
    return row, _assemble_row(DosProjectionsRow, row, projections)


def split_band_structure_row(
    row: BandStructureRow,
) -> tuple[BandStructureRow, BandStructureProjectionsRow | None]:
    """Split the projections of a band structure into their own row.

    The projections are removed from the band structure row so they are
    not held twice.

    Returns
    -----------
    BandStructureRow
        The row (the same object as the input) with no projections.
    BandStructureProjectionsRow or None
        None if the band structure has no projections.
    """
    projections = row.projections
    row.projections = None
    if projections is None:
        return row, None
    return row, _assemble_row(
        BandStructureProjectionsRow,
        row,
        projections,
        path_convention=row.path_convention,
    )


def dos_from_rows(
    dos: DosRow | ElectronicDos, projections: DosProjectionsRow | None = None
) -> ElectronicDos:
    """Rebuild a DOS from its row and, optionally, the row of its projections.

    Parameters
    -----------
    dos : DosRow
        The row of the total DOS table.
    projections : DosProjectionsRow or None
        The row of the projected DOS table with the same identifier, if the
        projections are wanted.

    Returns
    -----------
    ElectronicDos
        Which can be converted to a pymatgen object with `.to_pmg()`.
    """
    if projections is not None and projections.identifier != getattr(
        dos, "identifier", None
    ):
        raise ValueError(
            f"The projections of {projections.identifier} do not belong to the "
            f"DOS of {getattr(dos, 'identifier', None)}."
        )
    config = {name: getattr(dos, name) for name in ElectronicDos.model_fields}
    if projections is not None:
        config["projected_densities"] = ProjectedDos(
            **{name: getattr(projections, name) for name in ProjectedDos.model_fields}
        )
    return ElectronicDos(**config)


def band_structure_from_rows(
    band_structure: BandStructureRow | ElectronicBS,
    projections: BandStructureProjectionsRow | None = None,
) -> ElectronicBS:
    """Rebuild a band structure from its row and, optionally, its projections row.

    Parameters
    -----------
    band_structure : BandStructureRow
        The row of the band structure table.
    projections : BandStructureProjectionsRow or None
        The row of the projected band structure table with the same
        identifier, if the projections are wanted.

    Returns
    -----------
    ElectronicBS
        Which can be converted to a pymatgen object with `.to_pmg()`.
    """
    if projections is not None and projections.identifier != getattr(
        band_structure, "identifier", None
    ):
        raise ValueError(
            f"The projections of {projections.identifier} do not belong to the "
            f"band structure of {getattr(band_structure, 'identifier', None)}."
        )
    config = {name: getattr(band_structure, name) for name in ElectronicBS.model_fields}
    if projections is not None:
        config["projections"] = ProjectedBS(
            **{name: getattr(projections, name) for name in ProjectedBS.model_fields}
        )
    return ElectronicBS(**config)


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

    def _leaf_columns(self) -> list[tuple[str, bool]]:
        """The leaves of the schema by their path in a Parquet file, and whether they are float32.

        Parquet names the elements of lists `element`, whatever their Arrow name
        is. A writer ignores a path which is not in the file, so a path with another name
        does nothing, without an error.
        """
        import pyarrow as pa

        from emmet.core.arrow import arrowize

        schema = pa.schema(arrowize(self.row_model))
        leaves: list[tuple[str, bool]] = []

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
                leaves.append((path, pa.types.is_float32(dtype)))

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
        return [path for path, is_float32 in self._leaf_columns() if is_float32]

    @property
    def parquet_options(self) -> dict[str, Any]:
        """Keyword arguments for a pyarrow Parquet writer that encode the float32 columns well.

        BYTE_STREAM_SPLIT is used for the float32 columns, which needs dictionary encoding
        to be off for them: with both, the dictionary is used and BYTE_STREAM_SPLIT is
        silently ignored. It is wasted on floating point numbers anyway. Dictionary encoding
        is left on for the rest. Requires pyarrow.
        """
        leaves = self._leaf_columns()
        return {
            "use_byte_stream_split": [path for path, f32 in leaves if f32],
            "use_dictionary": [path for path, f32 in leaves if not f32],
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
