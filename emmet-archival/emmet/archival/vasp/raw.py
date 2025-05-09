"""Define archival formats for raw VASP calculation data."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING
from pathlib import Path
from pydantic import Field
from tempfile import TemporaryDirectory

import h5py
import numpy as np
import zarr

from monty.io import zopen
from pymatgen.io.vasp import Potcar

from pymatgen.io.validation.common import PotcarSummaryStats

from emmet.core.tasks import TaskDoc
from emmet.core.vasp.utils import VASP_RAW_DATA_ORG, discover_vasp_files, FileMetadata

from emmet.archival.base import Archiver

if TYPE_CHECKING:
    from collections.abc import Sequence
    from os import PathLike
    from typing_extensions import Self


class RawArchive(Archiver):
    """Archive a raw VASP calculation directory and remove copyright-protected info."""

    file_paths: dict[str, FileMetadata] = Field(
        description="A dict with the keys as hierarchies, and values as FileMetadata."
    )

    @staticmethod
    def convert_potcar_to_spec(potcar: str | Potcar) -> str:
        """Convert a VASP POTCAR to JSON-dumped string."""
        if isinstance(potcar, str):
            potcar = Potcar.from_str(potcar)
        return json.dumps(
            [p.model_dump() for p in PotcarSummaryStats.from_file(potcar)]
        )

    @classmethod
    def from_directory(cls, calc_dir: str | Path, **kwargs) -> Self:
        calc_dir = Path(calc_dir).resolve()
        if not calc_dir.exists():
            raise SystemError(f"Directory {calc_dir} does not exist!")

        file_paths: dict[str, FileMetadata] = {}
        for file_meta in discover_vasp_files(calc_dir):
            file_name = ".".join(file_meta.name.split(".")[:-1])
            ref_file_name = None
            for calc_type, base_file_names in VASP_RAW_DATA_ORG.items():
                if matches := sorted(
                    [f for f in base_file_names if f in file_name], key=lambda k: len(k)
                ):
                    ref_file_name = matches[
                        -1
                    ]  # ensures, e.g., INCAR.orig is matched over INCAR
                    break

            if not ref_file_name:
                continue

            file_paths[f"{calc_type}/{ref_file_name}"] = file_meta

        return cls(file_paths=file_paths)

    def _to_hdf5_like(self, group: h5py.Group | zarr.Group, **kwargs) -> None:
        """Add VASP files to an existing archival group."""
        for file_arch, file_meta in self.file_paths.items():
            if ".h5" in file_arch:
                arch = Path(file_arch)
                base_group = str(arch.parent)
                with zopen(file_meta.path, "rb") as vhf_b, h5py.File(
                    vhf_b, "r"
                ) as vh5f:
                    if base_group not in group:
                        group.create_group(base_group)
                    vh5f.copy("/", group[base_group], name=arch.name)
                if "vaspout" in file_arch:
                    ppath = str(arch / "input/potcar/content")
                    pdata = np.array(group[ppath]).tolist().decode()
                    group[file_arch]["input"]["potcar"].create_dataset(
                        "spec",
                        data=self.convert_potcar_to_spec(pdata),
                    )
                    del group[ppath]
                    group[file_arch].attrs["md5"] = file_meta.md5
                continue

            with zopen(file_meta.path, "rt") as _f:
                data = _f.read()

            file_key = file_arch
            if "POTCAR" in file_arch and "spec" not in file_arch:
                if len(_split_arch := file_arch.split(".")) > 1:
                    file_key = ".".join([*_split_arch[:-1], "spec", _split_arch[-1]])
                else:
                    file_key = f"{file_arch}.spec"
                data = self.convert_potcar_to_spec(data)

            group.create_dataset(file_key, data=[data], **kwargs)
            group[file_key].attrs["md5"] = file_meta.md5

    @classmethod
    def _extract_from_hdf5_like(
        cls,
        group: h5py.Group | zarr.Group,
        keys: Sequence[str] | None = None,
        output_dir: PathLike | None = None,
    ) -> list[FileMetadata]:
        output_dir = Path(output_dir or "calc_archive")
        if not output_dir.exists():
            output_dir.mkdir(exist_ok=True, parents=True)

        extracted_files = []
        if keys is None:
            keys = []
            group.visit(
                lambda x: keys.append(x)
                if getattr(group[x], "attrs", {}).get("md5")
                else None
            )

        for k in [_k for _k in keys if _k in group]:
            p = Path(k)

            if ".h5" in (file_name := p.name):
                with h5py.File(output_dir / file_name, "w") as f:
                    for _key in group[k]:
                        f.copy(group[k][_key], f, name=_key)
            else:
                with open(output_dir / file_name, "wt") as f:
                    f.write(np.array(group[k])[0].decode())

            extracted_files.append(FileMetadata(path=output_dir / file_name))
        return extracted_files

    @classmethod
    def to_task_doc(
        cls,
        archive_path: PathLike,
        group_key: str | None = None,
        **task_doc_kwargs,
    ) -> TaskDoc:
        """
        Create an emmet.core TaskDoc from an archived calculation directory.

        Parameters
        -----------
        archive_path : str | Path
            The name of the archive
        group_key : str | None = None
            If not None, the name of a file hierarchy to retrieve.
        **task_doc_kwargs
            kwargs to pass to TaskDoc.from_directory

        Returns
        -----------
        TaskDoc representing the calculation in the archive.
        """

        required_files = []
        group_key = group_key or ""
        for calc_type in ("input", "output", "workflow"):
            required_files.extend(
                [
                    f"{group_key}/{calc_type}/{fname}"
                    for fname in VASP_RAW_DATA_ORG[calc_type]
                ]
            )

        with TemporaryDirectory() as _tmp_dir:
            fm = cls.extract(archive_path, keys=required_files, output_dir=_tmp_dir)
            print(fm)
            task = TaskDoc.from_directory(_tmp_dir, **task_doc_kwargs)

        return task
