"""Define utilities needed for parsing VASP calculations."""
from __future__ import annotations
from collections import defaultdict
import os
from pathlib import Path
from pydantic import BaseModel, model_validator
from typing import TYPE_CHECKING

from emmet.core.utils import get_md5_blocked

if TYPE_CHECKING:
    from typing import Any
    from emmet.core.typing import PathLike


class FileMeta(BaseModel):
    """
    Lightweight model to enable validation on files via MD5.

    Fields:
        name (str) : Name of the VASP file without suffixes (e.g., INCAR)
        path (str) : Path to the VASP file
        md5 (str) : The MD5 checksum of the file. Does not need to be
            set, the model will populate it automatically from a
            valid file path.
    """

    name: str
    path: str
    md5: str

    @model_validator(mode="before")
    def check_path_md5(cls, v: Any) -> Any:
        """Ensure path is a str, and md5 file is populated."""
        if fp := v.get("path"):
            v["path"] = str(fp)
            if not v.get("md5") and Path(fp).exists():
                v["md5"] = get_md5_blocked(fp)
        return v


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
) -> list[str]:
    """
    Scan a target directory and identify VASP files.

    Parameters
    -----------
    target_dir : PathLike

    Returns
    -----------
    List of file names as str.
    """

    head_dir = Path(target_dir)
    vasp_files: list[str] = []

    with os.scandir(head_dir) as scan_dir:
        for p in scan_dir:
            # Check that at least one VASP file matches the file name
            if p.is_file() and any(f for f in _vasp_files if f in p.name):
                vasp_files.append(p.name)
    return vasp_files


def discover_and_sort_vasp_files(
    target_dir: PathLike,
) -> dict[str, list[str]]:
    """
    Find and sort VASP files from a directory for TaskDoc.

    Parameters
    -----------
    target_dir : PathLike

    Returns
    -----------
    dict of str (categories) to list of str (list of VASP files in
        that category)
    """
    by_type: dict[str, list[str]] = defaultdict(list)
    for _f in discover_vasp_files(target_dir):
        f = _f.lower()
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
) -> dict[Path, list[str]]:
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
    List of file names as str.
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
        tdir: PathLike, paths: dict[Path, list[str]]
    ) -> None:
        if Path(tdir).is_dir() and _path_depth_check(tdir):
            with os.scandir(tdir) as scan_dir:
                for p in scan_dir:
                    _recursive_discover_vasp_files(p, paths)

            if tpaths := discover_vasp_files(tdir):
                # Check if minimum number of VASP files are present
                # TODO: update with vaspout.h5 parsing
                if only_valid and any(
                    not any(f in file for file in tpaths) for f in REQUIRED_VASP_FILES
                ):
                    # Incomplete calculation input/output
                    return
                paths[Path(tdir).resolve()] = tpaths

    vasp_files: dict[Path, list[str]] = {}
    _recursive_discover_vasp_files(target_dir, vasp_files)
    return vasp_files
