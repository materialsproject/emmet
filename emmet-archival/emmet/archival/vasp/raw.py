"""Define archival formats for raw VASP calculation data."""
from __future__ import annotations

from typing import TYPE_CHECKING
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import h5py
import zarr

from monty.io import zopen
from emmet.core.tasks import _VOLUMETRIC_FILES, TaskDoc

from emmet.archival.base import Archiver, ArchivalFormat
from emmet.archival.utils import zpath
from emmet.archival.vasp import VASP_RAW_DATA_ORG, PotcarSpec

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any
    from typing_extensions import Self

@dataclass
class RawArchive(Archiver):
    """Archive a raw VASP calculation directory and remove copyright-protected info."""


    @classmethod
    def from_directory(cls, calc_dir: str | Path, **kwargs) -> Self:
        calc_dir = Path(calc_dir).resolve()
        if not calc_dir.exists():
            raise SystemError(f"Directory {calc_dir} does not exist!")

        metadata = {"calc_dir": str(calc_dir), "file_paths": {}}

        parsed_objects: dict[str, Any] = {}
        for calc_type, file_list in VASP_RAW_DATA_ORG.items():
            metadata["file_paths"][calc_type] = {}  # type: ignore[index]
            for file_name in file_list:
                if (file_path := zpath(calc_dir / file_name)).exists():
                    metadata["file_paths"][calc_type][file_name] = file_path  # type: ignore[index]

                    if file_name == "POTCAR":
                        parsed_objects["POTCAR_spec"] = str(PotcarSpec.from_file(file_path))
                    else:
                        with zopen(file_path, "rt") as f:
                            parsed_objects[file_name] = f.read()

        return cls(parsed_objects=parsed_objects, metadata=metadata, **kwargs)

    def to_group(
        self, group: h5py.Group | zarr.Group, group_key: str | None = None
    ) -> None:
        """Add VASP files to an existing archival group."""
        if group_key is not None:
            group.create_group(group_key)
            group = group[group_key]

        for calc_type, files in VASP_RAW_DATA_ORG.items():
            group.create_group(calc_type)

            for file_name in files:
                if (rawf := self.parsed_objects.get(file_name)) is None:
                    continue

                kwargs = self.compression.copy()
                if self.format == ArchivalFormat.HDF5:
                    kwargs.update(dtype=h5py.string_dtype(length=len(rawf)))

                group[calc_type].create_dataset(
                    file_name, data=[rawf], shape=1, **kwargs
                )
                if (
                    fpath := self.metadata.get("file_paths", {}).get(file_name)
                ) is not None:
                    group[calc_type][file_name].attrs[f"{file_name}_path"] = str(fpath)

    @classmethod
    def to_task_doc(
        cls,
        archive_name : str | Path,
        fmt: str | ArchivalFormat | None = None,
        group_key : str | None = None,
        **task_doc_kwargs
    ) -> TaskDoc:
        """
        Create an emmet.core TaskDoc from an archived calculation directory.

        Parameters
        -----------
        archive_name : str | Path
            The name of the archive
        fmt: str | ArchivalFormat | None = None,
            The format of the archive if not None, determined automatically otherwise.
        group_key : str | None = None
            If not None, the name of a file hierarchy to retrieve.
        **task_doc_kwargs
            kwargs to pass to TaskDoc.from_directory

        Returns
        -----------
        TaskDoc representing the calculation in the archive.
        """
        
        required_files = []
        for calc_type in ("input","output","workflow"):
            required_files.extend(
                [f"{calc_type}/{fname}" for fname in VASP_RAW_DATA_ORG[calc_type]]
            )

        required_files.extend(
            [f"volumetric/{fname}" for fname in task_doc_kwargs.get("volumetric_files",_VOLUMETRIC_FILES)]
        )
        
        with cls.load_archive(archive_name, fmt=fmt, group_key=group_key) as group:

            with TemporaryDirectory() as _tmp_dir:
                tmp_dir = Path(_tmp_dir)
                for file_harch in required_files:
                    file_name = Path(file_harch).name
                    if (_dset := group.get(file_harch) ) is not None:
                        with open(tmp_dir / file_name, "wb") as f:
                            f.write(list(_dset)[0])
                task = TaskDoc.from_directory(tmp_dir,**task_doc_kwargs)

        return task