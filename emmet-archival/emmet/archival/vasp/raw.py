"""Define archival formats for raw VASP calculation data."""

from __future__ import annotations

import hashlib
import orjson
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING

import h5py
import numpy as np
import zarr
from monty.io import zopen
from pydantic import Field
from emmet.core.io.pymatgen import (
    Structure,
    PotcarSummaryStats,
    VaspFiles,
    VaspValidator,
    Incar,
    Kpoints,
    Outcar,
    Potcar,
    Vasprun,
)

from emmet.archival.core import walk_hierarchical_data, FileArchiveBase
from emmet.archival.vasp.metadata import ArchiveMetadata
from emmet.core.tasks import TaskDoc
from emmet.core.vasp.calculation import PotcarSpec
from emmet.core.vasp.utils import (
    COMPRESSION_EXTENSIONS,
    DEFAULT_CALC_SUFFIXES,
    PARCHG_ALL_PARTS,
    STANDARD_CALC_SUFFIX,
    VASP_RAW_DATA_ORG,
    FileMetadata,
    check_vasp_file_name,
    discover_calculations,
    parse_vasp_file_name,
)

if TYPE_CHECKING:
    from collections.abc import MutableMapping, Sequence
    from os import PathLike
    from typing import Any, Self

    from emmet.core.types.typing import FSPathType


def _archive_key(file_name: str, suffixes: Sequence[str]) -> str:
    """The key of a VASP file in an archive: `{category}/{file name}`.

    The file name is the type of the file, e.g., INCAR, vasprun.xml, CHGCAR,
    with `.orig` for original inputs, and without the calculation suffix and
    compression extension. Raw POTCARs are archived as their spec,
    POTCAR.spec. The indices of PARCHG files and the temperature of
    electron-phonon POSCARs are kept, so that these files do not overwrite
    each other: PARCHG.0001.0002, POSCAR.T=300.

    Raises a ValueError if the file is not a VASP file or has unrecognized parts.
    """
    parsed = check_vasp_file_name(file_name, suffixes)
    name = parsed.file_type
    if name == "POTCAR":
        name = "POTCAR.spec"

    base = Path(file_name).name
    while base.endswith(COMPRESSION_EXTENSIONS):
        base = base.rsplit(".", 1)[0]
    extra = base.split(".")[1:]
    if parsed.file_type == "PARCHG":
        name += "".join(f".{p}" for p in extra if p.isdigit() or p in PARCHG_ALL_PARTS)
    elif parsed.file_type == "POSCAR.T":
        name = next(f"POSCAR.{p}" for p in extra if p.startswith("T="))

    if parsed.is_orig:
        name += ".orig"
    return f"{parsed.category}/{name}"


def raw_archive_hierarchy_from_files(
    file_metas: Sequence[FileMetadata],
    calc_suffix: str | None = None,
    suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
) -> dict[str, FileMetadata]:
    """Arrange the files of one calculation into the hierarchy of RawArchive.

    Every file is checked before anything is returned, so a calculation is never
    archived with some of its files left out.

    Parameters
    -----------
    file_metas : sequence of FileMetadata
        The files of one calculation.
    calc_suffix : str or None
        The suffix of the calculation. If not None, files whose names have
        a different calculation suffix are not accepted. Files with no suffix
        are always accepted, as they can be shared between the
        calculations of a directory.
    suffixes : sequence of str
        The calculation suffixes which file names can have. This must be
        the same as those used to find the files.

    Returns
    -----------
    dict of str to FileMetadata
        The files by their key in the archive, e.g., `output/vasprun.xml`.

    Raises
    -----------
    ValueError
        If a file is not a VASP file, has unrecognized parts in its name, has the
        suffix of another calculation, or if two files have the same key.
    """
    file_paths: dict[str, FileMetadata] = {}
    for file_meta in file_metas:
        name = file_meta.path.name
        key = _archive_key(name, suffixes)
        file_suffix = check_vasp_file_name(name, suffixes).calc_suffix
        if (
            calc_suffix is not None
            and file_suffix is not None
            and file_suffix != calc_suffix
        ):
            raise ValueError(
                f"{file_meta.path}: the file is for the calculation '{file_suffix}', "
                f"and cannot be archived with the calculation '{calc_suffix}'."
            )
        if key in file_paths:
            raise ValueError(
                f"{file_meta.path} and {file_paths[key].path} are both {key} "
                "in the archive. Only one can be archived per calculation."
            )
        file_paths[key] = file_meta
    return file_paths


def _isoformat_mtime(path: Path) -> str:
    """The modification time of a file as an ISO-8601 UTC string."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


class RawArchive(FileArchiveBase):
    """Archive the raw files of one VASP calculation and remove copyright-protected info."""

    file_paths: dict[str, FileMetadata] = Field(
        description="A dict with the keys as hierarchies, and values as FileMetadata."
    )
    calc_suffix: str = Field(
        STANDARD_CALC_SUFFIX,
        description="The suffix of the calculation, or standard if it has none.",
    )
    root: Path | None = Field(
        None,
        description="The directory which the original names of the files are relative to.",
    )

    @staticmethod
    def convert_potcar_to_spec(potcar: str | Potcar) -> bytes:
        """Convert a VASP POTCAR to JSON-dumped string."""

        pot_obj = Potcar.from_str(potcar) if isinstance(potcar, str) else potcar

        # Note that to accommodate both validation and TaskDoc, we need to
        # store the LEXCH kwarg here
        return orjson.dumps(
            [
                {**p.model_dump(), "lexch": pot_obj[i].LEXCH}
                for i, p in enumerate(PotcarSpec.from_potcar(pot_obj))
            ]
        )

    @classmethod
    def from_files(
        cls,
        files: Sequence[FileMetadata],
        root: str | Path | None = None,
        calc_suffix: str = STANDARD_CALC_SUFFIX,
        suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
    ) -> Self:
        """Create a RawArchive from the files of one calculation.

        Parameters
        -----------
        files : sequence of FileMetadata
            The files of the calculation, including any files shared with
            other calculations of its directory, e.g., a POTCAR.
        root : str or Path or None
            The directory the files are found in. The original names stored in
            the archive are the paths of the files relative to it, so that the
            archive does not reveal where the files were. Defaults to the
            names of the files only.
        calc_suffix : str
            The suffix of the calculation, or standard if it has none.
        suffixes : sequence of str
            The calculation suffixes which file names can have. This must be
            the same as those used to find the files.

        Raises
        -----------
        ValueError
            If any of the files cannot be archived, see `raw_archive_hierarchy_from_files`.
            Nothing is archived unless all of them can.
        """
        return cls(
            file_paths=raw_archive_hierarchy_from_files(
                files, calc_suffix=calc_suffix, suffixes=suffixes
            ),
            calc_suffix=calc_suffix,
            root=Path(root).resolve() if root is not None else None,
        )

    @classmethod
    def from_directory(
        cls,
        calc_dir: str | Path,
        suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
        require_vasprun: bool = True,
    ) -> list[Self]:
        """Create RawArchives from a directory, one for each calculation in it.

        The calculations of a directory, and the files which they share, are found
        with `emmet.core.vasp.utils.discover_calculations`.

        Parameters
        -----------
        calc_dir : str or Path
            Directory with VASP files
        suffixes : sequence of str
            The suffixes of the calculations in the directory, in the order
            they were run.
        require_vasprun : bool = True
            Whether to only archive calculations which have a vasprun.xml.

        Returns
        -----------
        list of RawArchive
            In the order that the calculations were run.
        """
        calc_dir = Path(calc_dir).resolve()
        if not calc_dir.exists():
            raise SystemError(f"Directory {calc_dir} does not exist!")

        return [
            cls.from_files(
                [FileMetadata(name=p.name, path=p) for p in files.file_paths()],
                root=locator.path,
                calc_suffix=locator.modifier or STANDARD_CALC_SUFFIX,
                suffixes=suffixes,
            )
            for locator, files in discover_calculations(
                calc_dir, suffixes, require_vasprun=require_vasprun
            ).items()
        ]

    def to_archive(  # type: ignore[override]
        self,
        file_name: FSPathType,
        metadata: ArchiveMetadata | dict[str, Any],
        compression: dict | None = None,
        zarr_store: MutableMapping | None = None,
    ) -> None:
        """Write the archive.

        Parameters
        -----------
        file_name (str or Path) : the name of the archive
        metadata : ArchiveMetadata or dict
            The metadata of the archive, see `ArchiveMetadata`. A dict is
            validated against it, and the `calc_suffix` of the archive is
            used if it has none. Nothing is written if it is not valid.
        compression (dict[str,Any] or None) : If specified, compression
            kwargs to pass to the file writer.
        zarr_store : MutableMapping or None (default)
            If specified, the ZARR store to begin file root at.
        """
        if not isinstance(metadata, ArchiveMetadata):
            metadata = ArchiveMetadata(**{"calc_suffix": self.calc_suffix, **metadata})
        if metadata.calc_suffix != self.calc_suffix:
            raise ValueError(
                f"The metadata is for the calculation '{metadata.calc_suffix}', "
                f"but the archive is of the calculation '{self.calc_suffix}'."
            )
        super().to_archive(
            file_name,
            metadata=metadata.to_attrs(),
            compression=compression,
            zarr_store=zarr_store,
        )

    def _original_name(self, path: Path) -> str:
        """The name of a file relative to the root, or just its name."""
        if self.root is not None:
            try:
                return path.resolve().relative_to(self.root).as_posix()
            except ValueError:
                pass
        return path.name

    def _to_hdf5_like(self, group: h5py.Group | zarr.Group, **kwargs) -> None:
        """Add VASP files to an existing archival group."""

        for file_arch, file_meta in self.file_paths.items():
            content_md5: str | None = None
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
                        self._writeout(
                            group[file_arch]["input/potcar"],  # type: ignore[index]
                            "spec",
                            pspec,
                            compress=False,
                        )
                    del group[ppath]

            else:
                # insert plaintext / binary files into HDF5 datasets
                with zopen(file_meta.path, "rb") as _f:
                    data: bytes = _f.read()

                if len(data) == 0:
                    continue

                file_key = file_arch
                parsed = parse_vasp_file_name(file_meta.path.name)
                if parsed is not None and parsed.file_type == "POTCAR":
                    # raw POTCARs are archived as their spec, the key already is
                    data = self.convert_potcar_to_spec(data.decode())

                content_md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
                self._writeout(group, file_key, data)

            attrs = group[file_key].attrs
            attrs["original_name"] = self._original_name(file_meta.path)
            attrs["mtime"] = _isoformat_mtime(file_meta.path)
            attrs["md5"] = str(
                file_meta.compute_hash() if file_meta.hash is None else file_meta.hash
            )
            if content_md5 is not None:
                attrs["content_md5"] = content_md5

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
        keys = walk_hierarchical_data(group) if keys is None else keys

        non_hdf5_datasets = [_k for _k in keys if _k in group and ".h5" not in _k]
        hdf5_groups = set()
        for k in set(keys).difference(non_hdf5_datasets):
            if ".h5" not in k:
                continue
            group_str = k.split(".h5", 1)[0] + ".h5"
            if isinstance(group.get(group_str), h5py.Group | zarr.Group):
                hdf5_groups.add(group_str)

        for k in non_hdf5_datasets + list(hdf5_groups):
            p = Path(k)
            if ".h5" in (file_name := p.name):
                with h5py.File(output_dir / file_name, "w") as f:
                    for _key in group[k]:  # type: ignore[union-attr]
                        f.copy(group[k][_key], f, name=_key)  # type: ignore[index]
            else:
                (output_dir / file_name).write_bytes(cls._readout(group, k))

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

                    data = cls._readout(group, key)
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
                                for ps in orjson.loads(data)
                            ]
                        elif fname == "poscar":
                            vasp_io["user_input"]["structure"] = Structure.from_str(
                                data.decode(), fmt="poscar"
                            )
                        else:
                            vasp_io["user_input"][fname] = fname_to_type[fname].from_str(  # type: ignore[attr-defined]
                                data.decode(),
                            )
                    else:
                        # These methods must write to a temp file to parse
                        with NamedTemporaryFile() as temp_file:
                            temp_file.write(data)
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
