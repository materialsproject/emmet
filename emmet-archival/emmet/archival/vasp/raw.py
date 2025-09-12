"""Define archival formats for raw VASP calculation data."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from pathlib import Path
from pydantic import Field
from tempfile import TemporaryDirectory, NamedTemporaryFile

import h5py
import numpy as np
import zarr

from monty.io import zopen
from pymatgen.core import Structure
from pymatgen.io.vasp import Incar, Kpoints, Potcar, Outcar, Vasprun

from pymatgen.io.validation.common import PotcarSummaryStats, VaspFiles
from pymatgen.io.validation.validation import VaspValidator

from emmet.core.tasks import TaskDoc
from emmet.core.vasp.calculation import PotcarSpec
from emmet.core.vasp.utils import VASP_RAW_DATA_ORG, discover_vasp_files, FileMetadata

from emmet.archival.base import Archiver

if TYPE_CHECKING:
    from collections.abc import Sequence, MutableMapping
    from os import PathLike
    from typing import Any
    from typing_extensions import Self


def raw_archive_hierarchy_from_files(
    file_metas: list[FileMetadata],
) -> dict[str, FileMetadata]:
    """Arrange files into the hierarchical structure expected by RawArchive.

    Parameters
    -----------
    file_metas : list of FileMetadata

    Returns
    -----------
    dict of str to FileMetadata
        The same input FileMetadata but in the hierarchical
        structure expected by RawArchive.
    """
    file_paths: dict[str, FileMetadata] = {}
    for file_meta in file_metas:
        file_name = file_meta.name.rsplit(".", 1)[0]
        ref_file_name = None
        for calc_type, base_file_names in VASP_RAW_DATA_ORG.items():
            if matches := sorted(
                [f for f in base_file_names if f in file_name], key=lambda k: len(k)
            ):
                # This ensures, e.g., INCAR.orig is matched instead of INCAR
                ref_file_name = matches[-1]
                break

        if not ref_file_name:
            continue

        file_paths[f"{calc_type}/{ref_file_name}"] = file_meta
    return file_paths


class RawArchive(Archiver):
    """Archive a raw VASP calculation directory and remove copyright-protected info."""

    file_paths: dict[str, FileMetadata] = Field(
        description="A dict with the keys as hierarchies, and values as FileMetadata."
    )

    @staticmethod
    def convert_potcar_to_spec(potcar: str | Potcar) -> str:
        """Convert a VASP POTCAR to JSON-dumped string."""

        if isinstance(potcar, str):
            pot_obj = Potcar.from_str(potcar)
        else:
            pot_obj = potcar

        # Note that to accommodate both validation and TaskDoc, we need to
        # store the LEXCH kwarg here
        return json.dumps(
            [
                {**p.model_dump(), "lexch": pot_obj[i].LEXCH}
                for i, p in enumerate(PotcarSpec.from_potcar(pot_obj))
            ]
        )

    @classmethod
    def from_directory(cls, calc_dir: str | Path) -> Self:
        """Create a RawArchive from a directory.

        Parameters
        -----------
        calc_dir : str or Path
            Directory with VASP files
        """
        calc_dir = Path(calc_dir).resolve()
        if not calc_dir.exists():
            raise SystemError(f"Directory {calc_dir} does not exist!")

        flat_file_paths = []
        for file_paths_by_suffix in discover_vasp_files(calc_dir).values():
            flat_file_paths.extend(file_paths_by_suffix)
        file_paths = raw_archive_hierarchy_from_files(flat_file_paths)

        return cls(file_paths=file_paths)

    def _to_hdf5_like(self, group: h5py.Group | zarr.Group, **kwargs) -> None:
        """Add VASP files to an existing archival group."""

        if isinstance(group, h5py.Group):
            dataset_constructor = "create_dataset"
        else:
            dataset_constructor = "create_array"

        for file_arch, file_meta in self.file_paths.items():
            if ".h5" in file_arch:
                file_key = file_arch
                # insert HDF5 files into output
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
                    pspec = self.convert_potcar_to_spec(pdata)

                    # mypy has a lot of issues with h5py / zarr Group-like objects
                    if "spec" in group[file_arch]["input/potcar"]:  # type: ignore[operator,index]
                        old_spec = group[file_arch]["input/potcar/spec"]  # type: ignore[index]
                        old_spec[...] = pspec  # type: ignore[index]
                    else:
                        getattr(group[file_arch]["input/potcar"], dataset_constructor)(  # type: ignore[union-attr,index]
                            "spec",
                            data=pspec,
                        )
                    del group[ppath]

            else:
                # insert plaintext / binary files into HDF5 datasets
                with zopen(file_meta.path, "rt") as _f:
                    data: str = _f.read()  # type: ignore[assignment]

                file_key = file_arch
                if "POTCAR" in file_arch and "spec" not in file_arch:
                    if len(_split_arch := file_arch.rsplit(".", 1)) > 1:
                        file_key = f"{_split_arch[0]}.spec.{_split_arch[1]}"
                    else:
                        file_key = f"{file_arch}.spec"
                    data = self.convert_potcar_to_spec(data)

                getattr(group, dataset_constructor)(file_key, data=[data], **kwargs)

            group[file_key].attrs["file_path"] = str(file_meta.path)
            group[file_key].attrs["md5"] = str(
                file_meta.compute_hash() if file_meta.hash is None else file_meta.hash
            )

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
            group.visit(  # type: ignore[union-attr]
                lambda x: (
                    keys.append(x)
                    if getattr(group[x], "attrs", {}).get("md5")
                    else None
                )
            )

        for k in [_k for _k in keys if _k in group]:
            p = Path(k)

            if ".h5" in (file_name := p.name):
                with h5py.File(output_dir / file_name, "w") as f:
                    for _key in group[k]:  # type: ignore[union-attr]
                        f.copy(group[k][_key], f, name=_key)  # type: ignore[index]
            else:
                with open(output_dir / file_name, "wt") as f:
                    f.write(np.array(group[k])[0].decode())

            extracted_files.append(
                FileMetadata(name=file_name, path=output_dir / file_name)
            )
        return extracted_files

    @classmethod
    def _validate(
        cls,
        archive_path: PathLike,
        group_key: str | None = None,
        files_to_extract: list[str] | None = None,
        zarr_store: MutableMapping | None = None,
        **kwargs,
    ) -> VaspValidator:
        """
        Validate a VASP calculation from an archive.

        Parameters
        -----------
        archive_path : PathLike
            Name of the archive.
        group_key : str or None (default)
            If a str, the name of the group in the archive to prefix from.
        files_to_extract : list[str] or None
            If specified, this is a list of all keys in the archive which
            should be extracted for validation.
            Defaults to the minimal files needed for a comprehensive validation.
        zarr_store : MutableMapping or None (default)
            If specified, the ZARR store to begin file root at.
        **kwargs to pass to VaspValidator.from_vasp_input
        """

        files_to_extract = files_to_extract or [
            *[f"input/{k}" for k in ("INCAR", "KPOINTS", "POSCAR", "POTCAR.spec")],
            *[f"output/{k}" for k in ("OUTCAR", "vasprun.xml")],
        ]

        fname_to_type: dict[str, type] = {
            "incar": Incar,
            "kpoints": Kpoints,
            "poscar": Structure,
            "potcar.spec": PotcarSpec,
            "outcar": Outcar,
            "vasprun.xml": Vasprun,
        }

        vasp_io: dict[str, dict[str, Any]] = {"user_input": {}}
        with cls._open_hdf5_like(
            archive_path, mode="r", group_key=group_key, zarr_store=zarr_store
        ) as group:
            for io_typ in ("input", "output"):
                for key in [
                    key for key in files_to_extract if io_typ in key and key in group
                ]:
                    if (fname := Path(key).name.lower()) not in fname_to_type:
                        continue

                    data = np.array(group[key])[0].decode()
                    if io_typ == "input":
                        # These methods can directly parse from in-memory str

                        if fname == "potcar.spec":
                            vasp_io["user_input"]["potcar"] = [
                                PotcarSummaryStats(
                                    keywords=ps["summary_stats"]["keywords"],
                                    stats=ps["summary_stats"]["stats"],
                                    titel=ps["titel"],
                                    lexch=ps["lexch"],
                                )
                                for ps in json.loads(data)
                            ]
                        elif fname == "poscar":
                            vasp_io["user_input"]["structure"] = Structure.from_str(
                                data, fmt="poscar"
                            )
                        else:
                            vasp_io["user_input"][fname] = fname_to_type[fname].from_str(  # type: ignore[attr-defined]
                                data,
                            )
                    else:
                        # These methods must write to a temp file to parse
                        with NamedTemporaryFile() as temp_file:
                            temp_file.write(np.array(group[key])[0])
                            temp_file.seek(0)
                            vasp_io[fname.split(".")[0]] = fname_to_type[fname](
                                temp_file.name
                            )

        vasp_files = VaspFiles(**vasp_io)  # type: ignore[arg-type]
        return VaspValidator.from_vasp_input(vasp_files=vasp_files, **kwargs)

    @classmethod
    def fast_validate(
        cls, archive_path: PathLike, group_key: str | None = None
    ) -> VaspValidator:
        """Perform a quick validation check on the calculation.

        This signature is intendended to match the pre-validation
        used in the new CLI:
        ```
        validated = VaspValidator.from_vasp_input(
            vasp_file_paths = {
                "incar": < path to INCAR>,
                "poscar": < path to POSCAR>,
                "potcar": < path to POTCAR>,
                "kpoints": < optional path to KPOINTS>,
            },
            fast = True
        )
        validated.valid # whether calculation is valid or not
        ```

        Parameters
        -----------
        archive_path : PathLike
            Name of the archive.
        group_key : str or None (default)
            If a str, the name of the group in the archive to prefix from.
        """
        return cls._validate(
            archive_path,
            group_key=group_key,
            files_to_extract=[
                f"input/{k}" for k in ("INCAR", "KPOINTS", "POSCAR", "POTCAR.spec")
            ],
            fast=True,
        )

    @classmethod
    def validate(
        cls, archive_path: PathLike, group_key: str | None = None
    ) -> VaspValidator:
        """Perform a normal validation check on the calculation.

        Parameters
        -----------
        archive_path : PathLike
            Name of the archive.
        group_key : str or None (default)
            If a str, the name of the group in the archive to prefix from.
        """
        return cls._validate(
            archive_path,
            group_key=group_key,
            fast=True,
        )

    @classmethod
    def to_task_doc(
        cls,
        archive_path: PathLike,
        group_key: str | None = None,
        zarr_store: MutableMapping | None = None,
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
        zarr_store : MutableMapping or None (default)
            If specified, the ZARR store to begin file root at.
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
            cls.extract(
                archive_path,
                keys=required_files,
                output_dir=_tmp_dir,
                zarr_store=zarr_store,
            )
            task = TaskDoc.from_directory(_tmp_dir, **task_doc_kwargs)

        return task
