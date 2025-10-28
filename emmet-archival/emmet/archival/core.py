"""Code agnostic archival tools."""

from __future__ import annotations

import gzip
import os
from typing import TYPE_CHECKING

import h5py
import numpy as np
from pydantic import Field
from pathlib import Path
import zarr

from emmet.archival.base import Archiver

if TYPE_CHECKING:
    from collections.abc import Sequence
    from os import PathLike
    from typing_extensions import Self


def _scan_dir(fsspec: Path, paths: list[Path], depth: int | None) -> None:

    if depth is not None and depth <= 0:
        return

    if (ap := Path(fsspec).absolute()).is_file():
        paths.append(ap)
    elif ap.is_dir():
        for x in os.scandir(ap):
            _scan_dir(x, paths, depth - 1 if depth is not None else None)


def _get_path_relative_to_parent(path: Path, parent: Path) -> Path:
    if not path.is_relative_to(parent):
        raise ValueError(f"Path {path} is not relative to {parent}")

    if path == parent:
        return Path("")

    for p in path.parents:
        if p == parent:
            break
    leaf = str(path).split(str(p), 1)[1]
    if leaf.startswith("/"):
        leaf = "." + leaf
    return Path(leaf)


def walk_hierarchical_data(
    hd: h5py.Group | zarr.Group,
    datasets: list[str],
    key: str = "/",
) -> None:
    """Walk a hierarchical dataset to find datasets.

    Parameters
    -----------
    hd : h5py.Group or zarr.Group
        The hierarchical data object
    datasets : list of str
        A list of full paths to each dataset
    key : str = "/"
        The key to access in `hd`, defaults to root "/"

    Returns
    -----------
    None. All dataset keys are stored in `dataset_keys`
    """
    if isinstance(hd[key], h5py.Dataset | zarr.Array):
        datasets.append(key)
    elif isinstance(hd[key], h5py.Group | zarr.Group):
        _ = [
            walk_hierarchical_data(hd, datasets, key=os.path.join(key, q))
            for q in hd[key]
        ]


class FileArchiveBase(Archiver):
    """Mix-in for HDF5 archival of raw text/bytes data."""

    @staticmethod
    def _compress(data: str | bytes) -> bytes:
        if isinstance(data, bytes) and data.startswith(b"\x1f\x8b"):
            return data
        return gzip.compress(data.encode() if isinstance(data, str) else data)

    @staticmethod
    def _decompress(data: bytes) -> bytes:
        if not data.startswith(b"\x1f\x8b"):
            return data
        return gzip.decompress(data)

    def _writeout(
        self,
        group: h5py.Group | zarr.Group,
        file_key: str,
        data: str | bytes,
        compress: bool = True,
    ) -> None:
        dset_cnstr = (
            group.create_dataset
            if isinstance(group, h5py.Group)
            else group.create_array
        )
        compressed = self._compress(data) if compress else data
        orig_len = len(compressed)
        dset = dset_cnstr(
            file_key,
            data=compressed,
            dtype=h5py.string_dtype(length=orig_len),
        )
        dset.attrs["len"] = orig_len

    @classmethod
    def _readout(
        cls, group: h5py.Group | zarr.Group, file_key: str, decompress: bool = True
    ) -> bytes:
        if (
            len(data := np.array(group[file_key]).tolist())
            < group[file_key].attrs["len"]
        ):
            # h5py strips out null bytes
            data += b"\x00" * (group[file_key].attrs["len"] - len(data))
        if file_key.endswith(".gz") or not decompress:
            return data
        return cls._decompress(data)


class FileArchive(FileArchiveBase):
    """Class supporting generic file archiving."""

    files: list[Path] = Field(description="The file paths to include.")

    def _to_hdf5_like(
        self,
        group: h5py.Group | zarr.Group,
        **kwargs,
    ) -> None:
        """Add files to hierarchical dataset."""

        fs = {p.parent for p in self.files}
        root = next(p for p in fs if all(q.is_relative_to(p) for q in fs))
        branches = list(
            map(
                str,
                sorted(
                    [_get_path_relative_to_parent(p, root) for p in fs if p != root],
                    key=lambda x: len(x.parents),
                ),
            )
        )
        for branch in branches:
            group.create_group(branch)

        for f in self.files:
            if (branch := _get_path_relative_to_parent(f.parent, root)) == Path("."):
                branch = "/"
            else:
                branch = str(branch)
            self._writeout(group[branch], f.name, f.read_bytes())

    @classmethod
    def _extract_from_hdf5_like(
        cls,
        group: h5py.Group | zarr.Group,
        keys: Sequence[str] | None = None,
        output_dir: PathLike | None = None,
    ) -> list[Path]:
        """Extract all files in a hierarchical archive."""

        output_dir = Path(output_dir or "calc_archive")

        extracted_files = []
        if keys is None:
            keys = []
            walk_hierarchical_data(group, keys)

        for k in [_k for _k in keys if _k in group]:
            p = output_dir / (k.split("/", 1)[1] if k.startswith("/") else k)
            if not p.parent.exists():
                p.parent.mkdir(exist_ok=True, parents=True)

            p.write_bytes(cls._readout(group, k))
            extracted_files.append(p)

        return extracted_files

    @classmethod
    def from_directory(
        cls,
        dir_name: str | Path,
        depth: int | None = 1,
    ) -> Self:

        paths: list[Path] = []
        _scan_dir(Path(dir_name), paths, depth + 1 if depth is not None else None)
        return cls(files=paths)
