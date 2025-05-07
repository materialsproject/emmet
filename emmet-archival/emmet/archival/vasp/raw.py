"""Define archival formats for raw VASP calculation data."""
from __future__ import annotations

from collections import defaultdict
import json
from typing import TYPE_CHECKING
from pathlib import Path
from tempfile import TemporaryDirectory, NamedTemporaryFile

import h5py
import zarr

from monty.io import zopen
from pymatgen.io.vasp.outputs import Vaspout

from pymatgen.io.validation.common import PotcarSummaryStats

from emmet.core.tasks import _VOLUMETRIC_FILES, TaskDoc
from emmet.core.vasp.utils import VASP_RAW_DATA_ORG, discover_vasp_files, FileMeta

from emmet.archival.base import Archiver, ArchivalFormat
from emmet.archival.utils import zpath

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self

class RawArchive(Archiver):
    """Archive a raw VASP calculation directory and remove copyright-protected info."""

    @classmethod
    def from_directory(cls, calc_dir: str | Path, **kwargs) -> Self:
        calc_dir = Path(calc_dir).resolve()
        if not calc_dir.exists():
            raise SystemError(f"Directory {calc_dir} does not exist!")

        metadata: dict[str, str | dict[str, str]] = {
            "calc_dir": str(calc_dir),
            "file_paths": defaultdict(dict),
            "md5": defaultdict(dict),
        }

        parsed_objects: dict[str, Any] = {}
        for file_name in discover_vasp_files(calc_dir):

            for calc_type, base_file_names in VASP_RAW_DATA_ORG.items():
                if (matches := sorted([f for f in base_file_names if f in file_name])):
                    ref_file_name = matches[-1] # ensures, e.g., INCAR.orig is matched over INCAR
                    break
                
            if not ref_file_name:
                continue
            
            file_meta = FileMeta(name = ref_file_name, path = calc_dir / file_name)
            metadata["file_paths"][calc_type][file_name] = str(file_meta.path)
            metadata["md5"][calc_type][file_name] = file_meta.md5

            if "POTCAR" in file_name:
                ps = PotcarSummaryStats.from_file(file_meta.path)
                parsed_objects[f"{file_name}.spec"] = json.dumps(
                    [p.model_dump() for p in ps]
                )
                metadata["file_paths"][calc_type][
                    f"{file_name}.spec"
                ] = metadata["file_paths"][calc_type].pop(file_name)
            elif file_name.startswith("vaspout.h5"):
                continue
            else:
                with zopen(file_meta.path, "rt") as f:
                    parsed_objects[file_name] = f.read()

        return cls(parsed_objects=parsed_objects, metadata=metadata, **kwargs)

    def to_group(
        self, group: h5py.Group | zarr.Group, group_key: str | None = None, **kwargs
    ) -> None:
        """Add VASP files to an existing archival group."""
        if group_key is not None:
            group.create_group(group_key)
            group = group[group_key]

        checksums = self.metadata.get("md5", {})

        for calc_type in VASP_RAW_DATA_ORG:
            group.create_group(calc_type)

            for file_name, file_path in self.metadata["file_paths"][calc_type].items():
                if file_name.endswith(".h5"):
                    if file_name == "vaspout.h5":
                        vout = Vaspout(file_path)

                        with NamedTemporaryFile() as vf:
                            vout.remove_potcar_and_write_file(vf.name)
                            with h5py.File(vf.name, "r") as f:
                                group[calc_type].copy(
                                    f, group[calc_type], name=file_name
                                )
                    else:
                        with h5py.File(file_path, "r") as f:
                            group[calc_type].create_dataset(
                                file_name,
                                data=f,
                            )

                if (rawf := self.parsed_objects.get(file_name)) is None:
                    continue

                compress_kwargs = kwargs.pop("compression",{}) or self.get_default_compression(self.format)
                if self.format == ArchivalFormat.HDF5:
                    kwargs.update(dtype=h5py.string_dtype(length=len(rawf)))

                group[calc_type].create_dataset(
                    file_name, data=[rawf], shape=1, **kwargs, **compress_kwargs
                )
                group[calc_type][file_name].attrs["path"] = str(file_path)
                if file_md5 := checksums.get(calc_type, {}).get(file_name):
                    group[calc_type][file_name].attrs["md5"] = file_md5

    @classmethod
    def to_task_doc(
        cls,
        archive_name: str | Path,
        fmt: str | ArchivalFormat | None = None,
        group_key: str | None = None,
        **task_doc_kwargs,
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
        for calc_type in ("input", "output", "workflow"):
            required_files.extend(
                [f"{calc_type}/{fname}" for fname in VASP_RAW_DATA_ORG[calc_type]]
            )

        required_files.extend(
            [
                f"volumetric/{fname}"
                for fname in task_doc_kwargs.get("volumetric_files", _VOLUMETRIC_FILES)
            ]
        )

        with cls.load_archive(archive_name, fmt=fmt, group_key=group_key) as group:
            with TemporaryDirectory() as _tmp_dir:
                tmp_dir = Path(_tmp_dir)
                for file_harch in required_files:
                    file_name = Path(file_harch).name
                    if (_dset := group.get(file_harch)) is not None:
                        with open(tmp_dir / file_name, "wb") as f:
                            f.write(list(_dset)[0])
                task = TaskDoc.from_directory(tmp_dir, **task_doc_kwargs)

        return task
