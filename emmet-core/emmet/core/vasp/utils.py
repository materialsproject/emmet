"""Define utilities needed for parsing VASP calculations."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    ["CHGCAR"] + [f"AECCAR{i}" for i in range(3)] + ["ELFCAR", "LOCPOT", "POT",]
)
VASP_OUTPUT_FILES = ["CONTCAR", "IBZKPT", "OSZICAR", "OUTCAR", "PCDAT", "PROCAR", "REPORT", "vasprun.xml", "vaspout.h5", "XDATCAR"]

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
    target_dir : str | Path,
    only_valid : bool = False,
) -> dict[Path,Sequence[str]]:
    """
    Walk a target directory and identify VASP files.

    Parameters
    -----------
    target_dir : str or Path
    only_valid : bool = False (default)
        Whether to only include directories which have the required
        minimum number of input and output files for parsing.

    Returns
    -----------
    dict of Path to list of file names as str.
    """

    head_dir = Path(target_dir)
    vasp_files = {}
    for file_name in _vasp_files:
        for p in head_dir.glob(f"**/{file_name}*"):
            if (calc_dir := p.parent.resolve() ) not in vasp_files:
                vasp_files[calc_dir] = []
            vasp_files[calc_dir].append(p.name)

    if only_valid:
        valid_vasp_files = {}
        for calc_dir, files in vasp_files.items():
            # TODO: update with vaspout.h5 parsing
            if all(
                any(f in file for file in files) for f in REQUIRED_VASP_FILES
            ):
                valid_vasp_files[calc_dir] = files.copy()
        return valid_vasp_files

    return vasp_files