"""Define utilities needed for parsing VASP calculations."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

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
    ["CHGCAR"]
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
    target_dir: str | Path,
) -> list[str]:
    """
    Scan a target directory and identify VASP files.

    Parameters
    -----------
    target_dir : str or Path

    Returns
    -----------
    List of file names as str.
    """

    head_dir = Path(target_dir)
    vasp_files: list[str] = []

    for _p in os.scandir(head_dir):
        p = Path(_p)
        matched_vasp_files = [f for f in _vasp_files if f in p.name]
        if len(matched_vasp_files) > 0:
            vasp_files.append(p.name)
    return vasp_files


def discover_and_sort_vasp_files(
    target_dir: str | Path,
) -> dict[str, list[str]]:
    categories = [
        "contcar_file",
        "elph_poscars",
        "outcar_file",
        "vasprun_file",
        "volumetric_files",
    ]
    by_type: dict[str, list[str]] = {category: [] for category in categories}
    for _f in discover_vasp_files(target_dir):
        f = _f.lower()
        is_ided = False
        for k in (
            "vasprun",
            "contcar",
            "outcar",
        ):
            if is_ided := k in f:
                by_type[f"{k}_file"].append(_f)
                break

        if not is_ided and any(vf in f for vf in VASP_VOLUMETRIC_FILES):
            by_type["volumetric_files"].append(_f)
        elif not is_ided and "poscar.t=" in f:
            by_type["elph_poscars"].append(_f)

    for category in categories:
        if len(by_type[category]) == 0:
            _ = by_type.pop(category)

    return by_type


def recursive_discover_vasp_files(
    target_dir: str | Path,
    only_valid: bool = False,
) -> dict[Path, list[str]]:
    """
    Recursively scan a target directory and identify VASP files.

    Parameters
    -----------
    target_dir : str or Path
    only_valid : bool = False (default)
        Whether to only include directories which have the required
        minimum number of input and output files for parsing.

    Returns
    -----------
    List of file names as str.
    """

    def _recursive_discover_vasp_files(
        tdir: str | Path, paths: dict[Path, list[str]]
    ) -> None:
        for _p in os.scandir(tdir):
            if (p := Path(_p)).is_dir():
                _recursive_discover_vasp_files(p, paths)
        if len(tpaths := discover_vasp_files(tdir)) > 0:
            paths[Path(tdir).resolve()] = tpaths

    vasp_files : dict[Path, list[str]] = {}
    _recursive_discover_vasp_files(target_dir, vasp_files)

    if only_valid:
        valid_vasp_files = {}
        for calc_dir, files in vasp_files.items():
            # TODO: update with vaspout.h5 parsing
            if all(any(f in file for file in files) for f in REQUIRED_VASP_FILES):
                valid_vasp_files[calc_dir] = files.copy()
        return valid_vasp_files

    return vasp_files
