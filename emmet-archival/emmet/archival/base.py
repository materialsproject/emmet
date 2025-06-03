"""Archival class definitions independent of data type."""

from __future__ import annotations

from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from pydantic import BaseModel
from typing import TYPE_CHECKING, Any

import h5py
from numcodecs import Blosc
import zarr


from emmet.archival.utils import StrEnum
import zarr.storage

if TYPE_CHECKING:
    from typing import Literal
    from collections.abc import Generator


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

    raise TypeError(
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
            with self._open_hdf5_like(
                file_name, fmt=fmt, mode="w", zarr_store=zarr_store
            ) as group:
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
            with cls._open_hdf5_like(
                archive_path, fmt=fmt, mode="r", zarr_store=zarr_store
            ) as _f:
                return cls._extract_from_hdf5_like(_f, *args, **kwargs)
        elif fmt == ArchivalFormat.PARQ:
            return cls._extract_from_parquet(archive_path, *args, **kwargs)
