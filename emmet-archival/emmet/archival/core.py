"""Code agnostic raw data archival tools."""

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

DEFAULT_RAW_ARCHIVE_NAME = Path("calc_archive")


def _scan_dir(fsspec: PathLike, depth: int | None) -> list[Path]:
    """Recursively scan a directory, accounting for depth relative to the parent.

    Parameters
    -----------
    fsspec : PathLike
        File or directory object to scan
    depth : int or None
        The maximum depth to which this function will search, see the docstr
        of `FileArchive.from_directory` for examples.

    Returns
    -----------
    list of Path
        List of scanned files.
    """
    paths: list[Path] = []

    def _scan_dir_with_paths(fsobj: PathLike, rem_depth: int | None) -> None:
        if rem_depth is not None and rem_depth <= 0:
            return

        if (ap := Path(fsobj).absolute()).is_file():
            paths.append(ap)
        elif ap.is_dir():
            for x in os.scandir(ap):
                _scan_dir_with_paths(
                    x, rem_depth - 1 if rem_depth is not None else None
                )

    _scan_dir_with_paths(fsspec, depth + 1 if depth is not None else None)
    return paths


def _get_path_relative_to_parent(path: Path, parent: Path) -> Path:
    """See if a target path is relative to a parent path, and extract the relative path.

    Raises a ValueError if `path` is not relative to `parent`

    Parameters
    -----------
    path : Path
        Target path
    parent : Path
        Parent path

    Returns
    -----------
    Path, the relative path between `parent` and `path` if
        `path` is relative to `parent`
    """
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
    key: str = "/",
) -> list[str]:
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

    datasets = []

    def _walk_hierarchical_data(g, k):
        if isinstance(g[k], h5py.Dataset | zarr.Array):
            datasets.append(k)
        elif isinstance(g[k], h5py.Group | zarr.Group):
            _ = [_walk_hierarchical_data(g, os.path.join(k, q)) for q in g[k]]

    _walk_hierarchical_data(hd, key)
    return datasets


class FileArchiveBase(Archiver):
    """Mix-in for HDF5 archival of raw text/bytes data."""

    @staticmethod
    def _compress(data: str | bytes) -> bytes:
        """Compress string or byte data using gzip if needed."""
        if isinstance(data, bytes) and data.startswith(b"\x1f\x8b"):
            return data
        return gzip.compress(data.encode() if isinstance(data, str) else data)

    @staticmethod
    def _decompress(data: bytes) -> bytes:
        """Decompress byte data using gzip if needed."""
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
        """Write and compress string data to a hierarchical dataset.

        Parameters
        -----------
        group : h5py or zarr Group
            The hierarchical data structure to add data to.
        file_key : str
            The name of the dataset / name of the file.
        data : str or bytes
            The contents of the data to write out.
        compress : bool = True
            Whether to compress data with gzip.
            With `compress` True, data which is already gzipped
            will not be re-gzipped.

        Returns
        -----------
        None, all data written to `group`.
        """
        dset_cnstr = (
            group.create_dataset
            if isinstance(group, h5py.Group)
            else group.create_array
        )
        compressed = self._compress(data) if compress else data
        orig_len = len(compressed)
        dset = dset_cnstr(
            file_key,
            data=compressed,  # type: ignore[arg-type]
            dtype=h5py.string_dtype(length=orig_len),
        )
        dset.attrs["len"] = orig_len

    @classmethod
    def _readout(
        cls, group: h5py.Group | zarr.Group, file_key: str, decompress: bool = True
    ) -> bytes:
        """Read and decompress string from a hierarchical dataset.

        Parameters
        -----------
        group : h5py or zarr Group
            The hierarchical data structure to read data from.
        file_key : str
            The name of the h5py.dataset or zarr.Array to extract.
        compress : bool = True
            Whether to compress data with gzip.
            With `compress` True, data which is not gzipped
            will not be re-gunzipped.

        Returns
        -----------
        bytes : the byte content of the dataset
        """
        if (
            len(data := np.array(group[file_key]).tolist())  # type: ignore[operator]
            < group[file_key].attrs["len"]
        ):
            # h5py strips out null bytes
            data += b"\x00" * (group[file_key].attrs["len"] - len(data))  # type: ignore[operator]
        if file_key.endswith(".gz") or not decompress:
            return data
        return cls._decompress(data)


class FileArchive(FileArchiveBase):
    """Class supporting generic file archiving.

    The intended use of this class is to archive raw data from
    postprocessing steps which produce non-VASP-like output,
    e.g., phonopy or LOBSTER output.

    Parameters
    -----------
    files : list of .Path
    """

    files: list[Path] = Field(description="The file paths to include.")

    def _to_hdf5_like(
        self,
        group: h5py.Group | zarr.Group,
        **kwargs,
    ) -> None:
        """Add files to hierarchical h5py or zarr Group.

        Note that because string data is handled uniquely by
        HDF5/zarr, the kwargs are ignored here but included
        to match the parent class signature.
        """

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
            if (_stem := _get_path_relative_to_parent(f.parent, root)) == Path("."):
                stem = "/"
            else:
                stem = str(_stem)
            self._writeout(group[stem], f.name, f.read_bytes())

    @classmethod
    def _extract_from_hdf5_like(
        cls,
        group: h5py.Group | zarr.Group,
        keys: Sequence[str] | None = None,
        output_dir: PathLike | None = None,
    ) -> list[Path]:
        """Extract all files in a hierarchical archive.

        Parameters
        -----------
        group : h5py or zarr .Group
        keys : list of str, or None (default)
            If a list of strings, the names of datasets with
            full hierarchical prefixing to retrieve.
            If None, retrieves all files.
        output_dir : Pathlike or None (default)
            Where to extract data to, defaults to `calc_archive`.

        Returns
        -----------
        list of Path
            The names of the extracted files.
        """

        output_dir = Path(output_dir or DEFAULT_RAW_ARCHIVE_NAME)

        extracted_files = []
        keys = walk_hierarchical_data(group) if keys is None else keys

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
        dir_name: PathLike,
        depth: int | None = 1,
    ) -> Self:
        """Ingest raw bytes data to prepare for hierarchical archiving.

        This class will create nested hierarchical data structures
        as needed to reflect the file system.

        Thus, a file structure like this:
            ./some_data.txt
            ./sub_dir/other_data.txt
            ./sub_dir/nested_sub_dir/even_more_data.txt
        will result in a hierarchical structure like this:
            /some_data.txt : h5py.Dataset or zarr.Array
            /sub_dir : h5py or zarr .Group
            /sub_dir/other_data.txt : h5py.Dataset or zarr.Array
            /sub_dir/nested_sub_dir/ : h5py or zarr .Group
            /sub_dir/nested_sub_dir/even_more_data.txt : h5py.Dataset or zarr.Array

        Parameters
        -----------
        dir_name : PathLike
            The name of the directory to ingest data from.
        depth : int or None, default = 1
            If an int, the maximum depth this constructor searches for data.
            In the example above, depth =
                1 would only save files in `sub_dir`
                2 save files in `sub_dir` and `sub_dir/nested_sub_dir`
                None save all files in `dir_name`, searching recursively

        Returns
        -----------
        FileArchive
        """
        return cls(files=_scan_dir(Path(dir_name), depth))
