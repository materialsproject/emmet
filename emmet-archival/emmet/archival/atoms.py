"""Archive collections of atoms (crystals, molecules,...)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np
from pydantic import Field
import pandas as pd
import pyarrow as pa
import zarr

from pymatgen.core import Element, Lattice, Structure, Species, PeriodicSite
from emmet.core.math import Matrix3D, ListVector3D

from emmet.archival.base import Archiver

if TYPE_CHECKING:
    from collections.abc import MutableMapping
    from typing import Any
    from typing_extensions import Self

_CARTESIAN = ("x", "y", "z")
_RECIPROCAL = ("a", "b", "c")
_VECTOR_SITE_PROPS = ("selective_dynamics", "velocities")


class CrystalArchive(Archiver):
    """Atomistic data for an ordered structure.

    Retains only lattice, atomic positions, and atomic identities.
    Could be used to represent structures from VASP output, e.g.,
    CHGCAR, where only this data is present.

    The fields on this class are flexible enough to store all atomistic
    info from crystallographic databases.
    """

    atomic_num: list[int] = Field(description="The atomic numbers.")
    direct_coords: list[ListVector3D] = Field(
        description="The coordinates of the atoms in units of the lattice vectors."
    )
    lattice: Matrix3D = Field(description="The lattice of crystal.")
    pbc: tuple[bool, bool, bool] = Field(
        (True, True, True),
        description="Whether periodic boundary conditions were used along each axis.",
    )
    oxi_states: list[float] | None = Field(
        None, description="The oxidation states on each site."
    )

    def _to_arrow_arrays(self, prefix: str | None = None) -> dict[str, pa.Array]:
        prefix = prefix or ""
        return {
            f"{prefix}{k}": pa.array([getattr(self, k)])
            for k in CrystalArchive.model_fields
        }

    def to_arrow(self) -> pa.Table:
        """Convert a structure to a pyarrow table."""
        return pa.table(self._to_arrow_arrays())

    @classmethod
    def from_arrow(cls, struct_table: pa.Table, prefix: str | None = None) -> Structure:
        """Create a pymatgen structure from a pyarrow table."""

        prefix = prefix or ""
        data = {
            k: struct_table[f"{prefix}{k}"].to_pylist()[0] for k in cls.model_fields
        }
        oxi_states = data["oxi_states"] or [
            None for _ in range(len(data["atomic_num"]))
        ]
        species: list[str | Element | Species] = []
        for i, z in enumerate(data["atomic_num"]):
            ele = Element.from_Z(z).value
            if oxi_states[i]:
                species.append(Species(ele, oxidation_state=oxi_states[i]))
            else:
                species.append(ele)
        return Structure(
            Lattice(data["lattice"], pbc=data["pbc"]),
            species,
            coords=data["direct_coords"],
            coords_are_cartesian=False,
        )

    @classmethod
    def from_pmg(cls, structure: Structure) -> Self:
        """Convert a pymatgen ordered structure to an archive."""
        if not structure.is_ordered:
            raise ValueError(
                "CrystalArchive can only be used for ordered structures - use StructureArchive instead."
            )
        _oxi_states = [
            [getattr(ion, "oxi_state", None) for ion in site.species][0]
            for site in structure
        ]
        oxi_states = None
        if any(_oxi_states):
            oxi_states = _oxi_states
        return cls(
            atomic_num=[site.species.elements[0].Z for site in structure],
            direct_coords=[site.frac_coords for site in structure],
            lattice=structure.lattice.matrix.tolist(),
            pbc=tuple(structure.pbc),
            oxi_states=oxi_states,
        )


class StructureArchive(Archiver):
    """Archive a pymatgen Structure."""

    structure: Structure = Field(description="The structure to archive.")

    @classmethod
    def from_file(cls, file_path: str | Path) -> Self:
        return cls(structure=Structure.from_file(file_path))

    @staticmethod
    def structure_to_columnar(structure: Structure) -> pd.DataFrame:
        cols = list(_RECIPROCAL)
        needs_oxi = any(hasattr(ele, "oxi_state") for ele in structure.composition)
        if structure.is_ordered:
            cols += ["atomic_num"]
            if needs_oxi:
                cols += ["oxi_state"]
        else:
            max_num_dis = max(len(site.species) for site in structure)
            for i in range(max_num_dis):
                new_cols = [f"atomic_num_{i}", f"occu_{i}"]
                if needs_oxi:
                    new_cols += [f"oxi_state_{i}"]
                cols.extend(new_cols)

        if structure.site_properties.get("magmom"):
            cols += ["magmom"]

        for k in (
            has_vector_site_props := set(_VECTOR_SITE_PROPS).intersection(
                structure.site_properties
            )
        ):
            if structure.site_properties.get(k):
                cols.extend([f"{k}_{vec_dir}" for vec_dir in _CARTESIAN])

        data: dict[str, list[Any]] = {
            k: [None for _ in range(len(structure))] for k in cols
        }
        for isite, site in enumerate(structure):
            if structure.is_ordered:
                data["atomic_num"][isite] = next(iter(site.species)).Z
                if oxi := getattr(site, "oxi_state", None):
                    data["oxi_state"][isite] = oxi
            else:
                for ispec, (species, occu) in enumerate(site.species.items()):
                    data[f"atomic_num_{ispec}"][isite] = species.Z
                    data[f"occu_{ispec}"][isite] = occu
                    if oxi := getattr(species, "oxi_state", None):
                        data[f"oxi_state_{ispec}"][isite] = oxi

            for iv, v in enumerate(_RECIPROCAL):
                data[v][isite] = site.frac_coords[iv]

            for k in has_vector_site_props:
                sp = site.properties.get(k, [None, None, None])
                for iv, v in enumerate(_CARTESIAN):
                    data[f"{k}_{v}"][isite] = sp[iv]

            if magmom := site.properties.get("magmom"):
                data["magmom"][isite] = magmom

        for k, v in data.items():  # type: ignore[assignment]
            if k.startswith("atomic_num"):
                _dtype = pd.Int64Dtype()
            elif k.startswith("selective_dynamics"):
                _dtype = pd.BooleanDtype()
            else:
                _dtype = pd.Float64Dtype()
            data[k] = pd.array(v, dtype=_dtype)

        columnar = pd.DataFrame(data)
        columnar.attrs = {
            "lattice": structure.lattice.matrix,
            "charge": structure.charge,
        }
        return columnar

    @staticmethod
    def columnar_to_structure(df: pd.DataFrame) -> Structure:
        sites: list[PeriodicSite] = []
        max_dis = len([col for col in df.columns if "occu" in col])
        has_oxi = any("oxi_state" in col for col in df.columns)
        has_vector_site_props = set(
            [k for k in _VECTOR_SITE_PROPS if any(k in col for col in df.columns)]
        )
        has_scalar_site_props = set(
            [k for k in ("magmom",) if any(k in col for col in df.columns)]
        )

        for isite in sorted(df.index):
            comp: MutableMapping[Element | Species, float] = defaultdict(float)
            if max_dis:
                for icomp in range(max_dis):
                    if (
                        pd.isna(df[f"atomic_num_{icomp}"][isite])
                        or df[f"atomic_num_{icomp}"][isite] < 0
                    ):
                        break

                    spec: Element | Species = Element.from_Z(
                        df[f"atomic_num_{icomp}"][isite]
                    )
                    if has_oxi and not pd.isna(oxi := df[f"oxi_state_{icomp}"][isite]):
                        spec = Species(spec.value, oxidation_state=oxi)
                    comp[spec] = df[f"occu_{icomp}"][isite]
            else:
                comp[Element.from_Z(df["atomic_num"][isite])] = 1

            props = {}
            for k in has_scalar_site_props:
                if not pd.isna(df[k][isite]):
                    props[k] = df[k][isite]
            for k in has_vector_site_props:
                if any(pd.isna(df[f"{k}_{v}"][isite]) for v in _CARTESIAN):
                    continue
                props[k] = [df[f"{k}_{v}"][isite] for v in _CARTESIAN]
            sites += [
                PeriodicSite(
                    dict(comp),
                    [df[v][isite] for v in _RECIPROCAL],
                    Lattice(df.attrs["lattice"]),
                    coords_are_cartesian=False,
                    properties=props or None,
                )
            ]
        return Structure.from_sites(sites, charge=df.attrs.get("charge"))

    def as_columnar(self) -> pd.DataFrame:
        return self.structure_to_columnar(self.structure)

    def _to_hdf5_like(self, group: h5py.Group | zarr.Group, **kwargs) -> None:
        cs = self.as_columnar()

        for k in (
            "lattice",
            "charge",
        ):
            if hasattr(v := cs.attrs[k], "tolist"):
                group.attrs[k] = v.tolist()
            else:
                group.attrs[k] = v

        group.attrs["columns"] = list(cs.columns)
        dtype = [(col, cs.dtypes[col].numpy_dtype) for col in cs.columns]
        int_cols = [
            idx for idx, dts in enumerate(dtype) if np.issubdtype(dts[1], np.integer)
        ]
        slist = cs.to_dict(orient="split")["data"]
        for idx in range(cs.shape[0]):
            for jdx in range(cs.shape[1]):
                if slist[idx][jdx] is None:
                    slist[idx][jdx] = -1 if jdx in int_cols else np.nan

        print(slist, dtype)
        group.create_dataset("structure", data=np.array(slist, dtype=dtype), **kwargs)

    @classmethod
    def _extract_from_hdf5_like(cls, group: h5py.Group | zarr.Group) -> Structure:
        data = {k: np.array(group[k]) for k in group}
        df = pd.DataFrame(data)
        df.attrs.update({k: group.attrs.get(k) for k in ("lattice", "charge")})
        return cls.columnar_to_structure(df)
