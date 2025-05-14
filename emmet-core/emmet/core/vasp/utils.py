"""Define utilities needed for parsing VASP calculations."""

from __future__ import annotations
from collections import defaultdict
import os
from pathlib import Path
from pydantic import BaseModel, Field, PrivateAttr, computed_field, model_validator
from typing import TYPE_CHECKING, Optional

from emmet.core.utils import get_md5_blocked

if TYPE_CHECKING:
    from typing import Any
    from emmet.core.typing import PathLike


class FileMetadata(BaseModel):
    """
    Lightweight model to enable validation on files via MD5.

    """

    path: Path = Field(description="Path to the file")
    _md5: Optional[str] = PrivateAttr(default=None)

    @model_validator(mode="before")
    def coerce_path(cls, v: Any) -> Any:
        """Coerce to path."""
        if "path" in v:
            path = v["path"]
            if not isinstance(path, Path):
                path = Path(path)
            v["path"] = path
        return v

    @property
    def name(self) -> str:
        """Return the name of the file."""
        return self.path.name

    @computed_field  # type:ignore[prop-decorator]
    @property
    def md5(self) -> Optional[str]:
        """MD5 checksum of the file (computed lazily if needed)."""
        if self._md5 is not None:
            return self._md5

        if self.validate_path_exists():
            try:
                self._md5 = get_md5_blocked(self.path)
            except Exception:
                self._md5 = None

        return self._md5

    def validate_path_exists(self):
        if not self.path.exists():
            raise ValueError(f"Path does not exist: {self.path}")
        if not self.path.is_file():
            raise ValueError(f"Path is not a file: {self.path}")
        return True

    def reset_md5(self):
        """Force recomputation of MD5 checksum on next call to md5 property."""
        self._md5 = None

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if not isinstance(other, FileMetadata):
            return NotImplemented
        return self.path == other.path


VASP_INPUT_FILES = [
    "INCAR",
    "KPOINTS",
    "KPOINTS_OPT",
    "POSCAR",
    "POTCAR",
    "POTCAR.spec",
    "vaspin.h5",
]
VASP_ELECTRONIC_STRUCTURE = [
    "EIGENVAL",
    "DOSCAR",
]
VASP_VOLUMETRIC_FILES = (
    [
        "CHGCAR",
        "CHG",
    ]
    + [f"AECCAR{i}" for i in range(3)]
    + [
        "ELFCAR",
        "LOCPOT",
        "POT",
    ]
)
VASP_OUTPUT_FILES = [
    "CONTCAR",
    "IBZKPT",
    "OSZICAR",
    "OUTCAR",
    "PCDAT",
    "PROCAR",
    "REPORT",
    "vasprun.xml",
    "vaspout.h5",
    "XDATCAR",
]

VASP_RAW_DATA_ORG = {
    "input": VASP_INPUT_FILES.copy(),
    "output": VASP_OUTPUT_FILES.copy(),
    "volumetric": VASP_VOLUMETRIC_FILES.copy(),
    "electronic_structure": VASP_ELECTRONIC_STRUCTURE.copy(),
    "workflow": ["FW.json", "custodian.json", "transformations.json"],
}

REQUIRED_VASP_FILES = ["INCAR", "POSCAR", "POTCAR", "CONTCAR", "OUTCAR", "vasprun.xml"]

_vasp_files = set()
for v in VASP_RAW_DATA_ORG.values():
    _vasp_files.update(v)

for f in VASP_INPUT_FILES:
    fspec = f.split(".")
    new_f = fspec[0] + ".orig"
    if len(fspec) > 1:
        new_f += "." + ".".join(fspec[1:])
    VASP_RAW_DATA_ORG["input"].append(new_f)


def discover_vasp_files(
    target_dir: PathLike,
) -> list[FileMetadata]:
    """
    Scan a target directory and identify VASP files.

    Parameters
    -----------
    target_dir : PathLike

    Returns
    -----------
    List of FileMetadata for the identified files.
    """

    head_dir = Path(target_dir)
    vasp_files: list[FileMetadata] = []

    with os.scandir(head_dir) as scan_dir:
        for p in scan_dir:
            # Check that at least one VASP file matches the file name
            if p.is_file() and any(f for f in _vasp_files if f in p.name):
                vasp_files.append(FileMetadata(path=Path(p.path)))
    return vasp_files


def discover_and_sort_vasp_files(
    target_dir: PathLike,
) -> dict[str, list[FileMetadata]]:
    """
    Find and sort VASP files from a directory for TaskDoc.

    Parameters
    -----------
    target_dir : PathLike

    Returns
    -----------
    dict of str (categories) to list of FileMetadata (list of VASP files in
        that category)
    """
    by_type: dict[str, list[FileMetadata]] = defaultdict(list)
    for _f in discover_vasp_files(target_dir):
        f = _f.name.lower()
        for k in (
            "vasprun",
            "contcar",
            "outcar",
        ):
            if k in f:
                by_type[f"{k}_file"].append(_f)
                break
        else:
            # NB: the POT file needs the extra `"potcar" not in f` check to ensure that
            # POTCARs are not classed as volumetric files.
            if any(
                vf.lower() in f and "potcar" not in f for vf in VASP_VOLUMETRIC_FILES
            ):
                by_type["volumetric_files"].append(_f)
            elif "poscar.t=" in f:
                by_type["elph_poscars"].append(_f)

    return by_type


def recursive_discover_vasp_files(
    target_dir: PathLike,
    only_valid: bool = False,
    max_depth: int | None = None,
) -> dict[Path, list[FileMetadata]]:
    """
    Recursively scan a target directory and identify VASP files.

    Parameters
    -----------
    target_dir : PathLike
    only_valid : bool = False (default)
        Whether to only include directories which have the required
        minimum number of input and output files for parsing.
    max_depth : int or None (default)
        If an int, the maximum depth with which directories are scanned
        for VASP files. For example, if max_depth == 1, this would only
        search `target_dir` and any immediate sub-directories in `target_dir`.

    Returns
    -----------
    dict of Path  to list of FileMetadata identified as VASP files.
    """

    head_dir = Path(target_dir).resolve()

    def _path_depth_check(tpath: PathLike) -> bool:
        if max_depth and (tp := Path(tpath).resolve()) != head_dir:
            for depth, parent in enumerate(tp.parents):
                if parent == head_dir:
                    break
            return depth + 1 <= max_depth
        return True

    def _recursive_discover_vasp_files(
        tdir: PathLike, paths: dict[Path, list[FileMetadata]]
    ) -> None:
        if Path(tdir).is_dir() and _path_depth_check(tdir):
            with os.scandir(tdir) as scan_dir:
                for p in scan_dir:
                    _recursive_discover_vasp_files(p, paths)

            if tpaths := discover_vasp_files(tdir):
                # Check if minimum number of VASP files are present
                # TODO: update with vaspout.h5 parsing
                if only_valid and any(
                    not any(f in file.name for file in tpaths)
                    for f in REQUIRED_VASP_FILES
                ):
                    # Incomplete calculation input/output
                    return
                paths[Path(tdir).resolve()] = tpaths

    vasp_files: dict[Path, list[FileMetadata]] = {}
    _recursive_discover_vasp_files(target_dir, vasp_files)
    return vasp_files
