"""Archival class definitions independent of data type."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from pydantic import BaseModel, Field
from typing import TYPE_CHECKING, Any

import h5py
from numcodecs import Blosc
import numpy as np
import pandas as pd
import zarr

from pymatgen.core import Element, Lattice, Structure, Species, PeriodicSite

from emmet.archival.utils import StrEnum

if TYPE_CHECKING:
    from collections.abc import Generator

_CARTESIAN = ("x", "y", "z")
_RECIPROCAL = ("a", "b", "c")
_VECTOR_SITE_PROPS = ("selective_dynamics", "velocities")


class ArchivalFormat(StrEnum):
    HDF5 = "h5"
    ZARR = "zarr"
    PARQ = "parquet"


def infer_archive_format(file_name: PathLike) -> ArchivalFormat:
    """
    Infer the format of a file.

    Parameters
    -----------
    file_name (PathLike) : The name of the file

    Returns
    -----------
    ArchivalFormat
    """
    archive_path = Path(file_name)
    for fmt in ArchivalFormat:
        if f".{fmt.value}" in archive_path.suffixes:
            return ArchivalFormat(fmt)

    raise ValueError(
        f"Unknown file format - recognized formats are:\n{', '.join(ArchivalFormat.__members__)}"
    )


class Archiver(BaseModel):
    """Define base archival methods."""

    @staticmethod
    def get_default_compression(format: ArchivalFormat) -> dict:
        if format == ArchivalFormat.HDF5:
            return {
                "compression": "gzip",
                "compression_opts": 9,
                "chunks": True,
            }
        elif format == ArchivalFormat.ZARR:
            return {
                "compressor": Blosc(clevel=9),
            }
        return {}

    def _to_hdf5_like(
        self,
        group: h5py.Group | zarr.Group,
        **kwargs,
    ) -> None:
        """Append data to an existing HDF5-like file group."""
        raise NotImplementedError

    def _to_parquet(self, file_name: PathLike, **kwargs) -> None:
        """Write data to a parquet file."""
        raise NotImplementedError

    def to_archive(
        self,
        file_name: PathLike = "archive.h5",
        metadata: dict[str, Any] | None = None,
        compression: dict | None = None,
    ) -> None:
        """Create a new data archive from the parsed objects.

        With no arguments passed, this function parses the files
        in `file_paths` and archives them to a file called `archive.h5`.

        Parameters
        -----------
        file_name (str or Path) : defaults to "archive.h5"
        metadata (dict[str,Any]) : JSON-like metadata, optional
        compression (dict[str,Any] or None) : If specified, compression
            kwargs to pass to the file writer.
        """

        fmt = infer_archive_format(file_name)
        compression = compression or self.get_default_compression(fmt)

        if fmt in (ArchivalFormat.HDF5, ArchivalFormat.ZARR):
            with Archiver.load_archive(file_name, fmt=fmt, mode="w") as group:
                self._to_hdf5_like(group, **compression)
                for k, v in (metadata or {}).items():
                    group.attrs[k] = v
        elif fmt == ArchivalFormat.PARQ:
            self._to_parquet(file_name, **compression)
        else:
            raise ValueError("Unknown file format")

    @classmethod
    def _extract_from_hdf5_like(
        cls, group: h5py.Group | zarr.Group, *args, **kwargs
    ) -> Any:
        """Extract data from an HDF5-like file."""
        raise NotImplementedError

    @classmethod
    def _extract_from_parquet(cls, archive_path: str | Path, *args, **kwargs) -> Any:
        """Extract data from a parquet file."""
        raise NotImplementedError

    @classmethod
    def extract(cls, archive_path: str | Path, *args, **kwargs) -> Any:
        """Extract data from an archive."""

        fmt = infer_archive_format(archive_path)
        if fmt in (ArchivalFormat.HDF5, ArchivalFormat.ZARR):
            with Archiver.load_archive(archive_path, fmt=fmt, mode="r") as _f:
                return cls._extract_from_hdf5_like(_f, *args, **kwargs)
        elif fmt == ArchivalFormat.PARQ:
            return cls._extract_from_parquet(archive_path, *args, **kwargs)

    @contextmanager
    @staticmethod
    def load_archive(
        archive_name: str | Path,
        fmt: str | ArchivalFormat | None = None,
        mode: str = "r",
        group_key: str | None = None,
    ) -> Generator:
        """
        Load an archive from a file name.

        Parameters
        -----------
        archive_name : str | Path
            The name of the archive file
        fmt: str | ArchivalFormat | None = None
        mode : str = "r"
            The mode to open the file in, either "r" or "w"
        group_key : str | None = None
            If not None, the name of a specific file hierarchy to retrieve.
        """

        fmt = fmt or infer_archive_format(archive_name)
        if fmt == ArchivalFormat.HDF5:
            group = h5py.File(archive_name, mode)
        elif fmt == ArchivalFormat.ZARR:
            group = zarr.open(archive_name, mode)
        else:
            raise TypeError(f"Unknown archive format {fmt}.")

        try:
            if group_key is not None:
                yield group[group_key]
            yield group

        finally:
            if fmt == ArchivalFormat.HDF5:
                # zarr automatically flushes data
                group.close()


class StructureArchive(Archiver):
    """Archive a pymatgen Structure."""

    structure: Structure = Field(description="The structure to archive.")

    @classmethod
    def from_file(cls, file_path: str | Path) -> StructureArchive:
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

        data = {k: [None for _ in range(len(structure))] for k in cols}
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
                data["magmom"].append(magmom)

        for k, v in data.items():
            if k.startswith("atomic_num"):
                _dtype = pd.Int64Dtype()
            elif k.startswith("selective_dynamics"):
                _dtype = pd.BooleanDtype()
            else:
                _dtype = pd.Float64Dtype()
            data[k] = pd.array(v, dtype=_dtype)
        data["_attributes"] = {
            "lattice": structure.lattice.matrix,
            "charge": structure.charge,
        }
        return data

    @staticmethod
    def columnar_to_structure(column_dict: dict[str, Any]) -> Structure:
        struct_meta = column_dict.pop("_attributes")
        df = pd.DataFrame(column_dict)
        sites = [None for _ in range(len(df))]
        max_dis = len([col for col in df.columns if "occu" in col])
        has_oxi = any("oxi_state" in col for col in df.columns)
        has_vector_site_props = set(
            [k for k in _VECTOR_SITE_PROPS if any(k in col for col in df.columns)]
        )
        has_scalar_site_props = set(
            [k for k in ("magmom",) if any(k in col for col in df.columns)]
        )

        for isite in df.index:
            if max_dis:
                comp = defaultdict(float)
                for icomp in range(max_dis):
                    if np.isnan(df[f"atomic_num_{icomp}"][isite]):
                        break
                    spec = Element.from_Z(df[f"atomic_num_{icomp}"][isite])
                    if has_oxi and not np.isnan(oxi := df[f"oxi_state_{icomp}"][isite]):
                        spec = Species(spec, oxidation_state=oxi)
                    print(spec)
                    comp[spec] = df[f"occu_{icomp}"][isite]
            else:
                comp = Element.from_Z(df["atomic_num"][isite])
            props = {}
            for k in has_scalar_site_props:
                if not np.isnan(df[k][isite]):
                    props[k] = df[k][isite]
            for k in has_vector_site_props:
                if any(np.isnan(df[f"{k}_{v}"][isite]) for v in _CARTESIAN):
                    continue
                props[k] = [df[f"{k}_{v}"][isite] for v in _CARTESIAN]
            sites[isite] = PeriodicSite(
                comp,
                [df[v][isite] for v in _RECIPROCAL],
                Lattice(struct_meta["lattice"]),
                coords_are_cartesian=False,
                properties=props or None,
            )
        return Structure.from_sites(sites, charge=struct_meta.get("charge"))

    def _to_hdf5_like(self, group: h5py.Group | zarr.Group, **kwargs) -> None:
        columnar_struct = self.structure_to_columnar(self.structure)

        struct_meta = columnar_struct.pop("_attributes")
        for k in ("lattice", "charge"):
            group.attrs[k] = struct_meta.get(k)

        columns = list(columnar_struct)
        for k in columns:
            group.create_dataset(k, data=columnar_struct[k], **kwargs)

        group.attrs["columns"] = columns

    @classmethod
    def _extract_from_hdf5_like(cls, group: h5py.Group | zarr.Group) -> Structure:
        data = {k: np.array(group[k]) for k in group}
        data["_attributes"] = {k: group.attrs.get(k) for k in ("lattice", "charge")}
        return cls.columnar_to_structure(data)
