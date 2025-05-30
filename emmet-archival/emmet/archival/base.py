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
import zarr.storage

if TYPE_CHECKING:
    from typing import Literal
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
            return fmt

    raise TypeError(f"Unknown file format - recognized formats are:\n{', '.join(ArchivalFormat.__members__)}")


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

    @staticmethod
    @contextmanager
    def _open_hdf5_like(
        archive_name: str | Path,
        fmt: str | ArchivalFormat | None = None,
        mode: Literal["r", "w", "a"] = "r",
        group_key: str | None = None,
        zarr_store: zarr.storage.Store | None = None,
    ) -> Generator:
        """
        Load an archive from a file name.

        Parameters
        -----------
        archive_name : str | Path
            The name of the archive file
        fmt: str | ArchivalFormat | None = None
        mode : str = "r"
            The mode to open the file in, either "r", "w", or "a".
        group_key : str | None = None
            If not None, the name of a specific file hierarchy to retrieve.
        zarr_store : zarr.storage.Store or None (default)
            If specified, the ZARR store to begin file root at.
            Could be an FSStore, default is same as ZARR's default: MemoryStore.
        """

        fmt = fmt or infer_archive_format(archive_name)
        if fmt == ArchivalFormat.HDF5:
            group = h5py.File(archive_name, mode)
        elif fmt == ArchivalFormat.ZARR:
            group = zarr.open_group(store=zarr_store, path=archive_name, mode=mode)
        else:
            raise TypeError(f"Specified format = {fmt} is not HDF5-like.")

        try:
            if group_key is not None:
                yield group[group_key]
            yield group

        finally:
            if fmt == ArchivalFormat.HDF5:
                # zarr automatically flushes data
                group.close()

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
        zarr_store: zarr.storage.Store | None = None,
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
        zarr_store : zarr.storage.Store or None (default)
            If specified, the ZARR store to begin file root at.
            Could be an FSStore, default is same as ZARR's default: MemoryStore.
        """

        fmt = infer_archive_format(file_name)
        compression = compression or self.get_default_compression(fmt)

        if fmt in (ArchivalFormat.HDF5, ArchivalFormat.ZARR):
            with self._open_hdf5_like(file_name, fmt=fmt, mode="w", zarr_store=zarr_store) as group:
                self._to_hdf5_like(group, **compression)
                for k, v in (metadata or {}).items():
                    group.attrs[k] = v
        elif fmt == ArchivalFormat.PARQ:
            self._to_parquet(file_name, **compression)
        else:
            raise ValueError("Unknown file format")

    @classmethod
    def _extract_from_hdf5_like(cls, group: h5py.Group | zarr.Group, *args, **kwargs) -> Any:
        """Extract data from an HDF5-like file."""
        raise NotImplementedError

    @classmethod
    def _extract_from_parquet(cls, archive_path: str | Path, *args, **kwargs) -> Any:
        """Extract data from a parquet file."""
        raise NotImplementedError

    @classmethod
    def extract(
        cls,
        archive_path: str | Path,
        zarr_store: zarr.storage.Store | None = None,
        *args,
        **kwargs,
    ) -> Any:
        """Extract data from an archive.

        Parameters
        -----------
        file_name (str or Path) : defaults to "archive.h5"
        zarr_store : zarr.storage.Store or None (default)
            If specified, the ZARR store to begin file root at.
            Could be an FSStore, default is same as ZARR's default: MemoryStore.
        *args : args to pass to _extract_from_{hdf5_like, parquet}
        **kwargs : kwargs to pass to _extract_from_{hdf5_like, parquet}
        """

        fmt = infer_archive_format(archive_path)
        if fmt in (ArchivalFormat.HDF5, ArchivalFormat.ZARR):
            with cls._open_hdf5_like(archive_path, fmt=fmt, mode="r", zarr_store=zarr_store) as _f:
                return cls._extract_from_hdf5_like(_f, *args, **kwargs)
        elif fmt == ArchivalFormat.PARQ:
            return cls._extract_from_parquet(archive_path, *args, **kwargs)


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

        for k in (has_vector_site_props := set(_VECTOR_SITE_PROPS).intersection(structure.site_properties)):
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

        columnar = pd.DataFrame(data)
        columnar.attrs = {
            "lattice": structure.lattice.matrix,
            "charge": structure.charge,
        }
        return columnar

    @staticmethod
    def columnar_to_structure(df: pd.DataFrame) -> Structure:
        sites = [None for _ in range(len(df))]
        max_dis = len([col for col in df.columns if "occu" in col])
        has_oxi = any("oxi_state" in col for col in df.columns)
        has_vector_site_props = set([k for k in _VECTOR_SITE_PROPS if any(k in col for col in df.columns)])
        has_scalar_site_props = set([k for k in ("magmom",) if any(k in col for col in df.columns)])

        for isite in df.index:
            if max_dis:
                comp = defaultdict(float)
                for icomp in range(max_dis):
                    if pd.isna(df[f"atomic_num_{icomp}"][isite]) or df[f"atomic_num_{icomp}"][isite] < 0:
                        break
                    spec = Element.from_Z(df[f"atomic_num_{icomp}"][isite])
                    if has_oxi and not pd.isna(oxi := df[f"oxi_state_{icomp}"][isite]):
                        spec = Species(spec, oxidation_state=oxi)
                    comp[spec] = df[f"occu_{icomp}"][isite]
            else:
                comp = Element.from_Z(df["atomic_num"][isite])
            props = {}
            for k in has_scalar_site_props:
                if not pd.isna(df[k][isite]):
                    props[k] = df[k][isite]
            for k in has_vector_site_props:
                if any(pd.isna(df[f"{k}_{v}"][isite]) for v in _CARTESIAN):
                    continue
                props[k] = [df[f"{k}_{v}"][isite] for v in _CARTESIAN]
            sites[isite] = PeriodicSite(
                comp,
                [df[v][isite] for v in _RECIPROCAL],
                Lattice(df.attrs["lattice"]),
                coords_are_cartesian=False,
                properties=props or None,
            )
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
        int_cols = [idx for idx, dts in enumerate(dtype) if np.issubdtype(dts[1], np.integer)]
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
