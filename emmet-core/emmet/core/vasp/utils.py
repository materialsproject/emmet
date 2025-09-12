"""Define utilities needed for parsing VASP calculations."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from emmet.core.utils import get_hash_blocked

if TYPE_CHECKING:
    from typing import Any

    from emmet.core.types.typing import FSPathType

logger = logging.getLogger(__name__)

TASK_NAMES = {"precondition"} | {f"relax{i+1}" for i in range(9)}


class FileMetadata(BaseModel):
    """
    Lightweight model to enable validation on files via MD5.

    """

    name: str = Field(
        description="Name of the VASP file without suffixes (e.g., INCAR)"
    )
    path: Path = Field(description="Path to the VASP file")
    hash: str | None = Field(
        description="Hash of the file (computed only when requested)",
        default=None,
    )

    @model_validator(mode="before")
    def coerce_path(cls, v: Any) -> Any:
        """Only coerce to Path. No existence check here."""
        if "path" in v:
            path = v["path"]
            if not isinstance(path, Path):
                path = Path(path)
            v["path"] = path
        return v

    def compute_hash(self) -> str | None:
        """Compute the hash of the file."""
        if self.validate_path_exists():
            try:
                self.hash = get_hash_blocked(self.path)
            except Exception:
                self.hash = None

        return self.hash

    def validate_path_exists(self):
        if not self.path.exists():
            raise ValueError(f"Path does not exist: {self.path}")
        if not self.path.is_file():
            raise ValueError(f"Path is not a file: {self.path}")
        return True

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if not isinstance(other, FileMetadata):
            return NotImplemented
        return self.path == other.path

    @property
    def calc_suffix(self) -> str:
        """Get any calculation-related suffixes, e.g., relax1."""
        suffix: str | None = None
        suffixes = self.path.suffixes
        for i in range(len(suffixes)):
            if (s := suffixes[-1 - i].split(".")[-1]) in TASK_NAMES:
                suffix = s
                break
        return suffix or "standard"


class CalculationLocator(BaseModel):
    """Object to represent calculation directory with possible file suffixes."""

    path: Path = Field(description="The path to the calculation directory")
    modifier: str | None = Field(
        description="Optional modifier for the calculation", default=None
    )

    def __hash__(self) -> int:
        # Resolve path to handle different representations of same path
        return hash((self.path.resolve(), self.modifier))

    # You might not need custom __eq__ in Pydantic v2
    # But if you keep it, consider path resolution:
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CalculationLocator):
            return False
        return (
            self.path.resolve() == other.path.resolve()
            and self.modifier == other.modifier
        )


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

REQUIRED_VASP_FILES = {"INCAR", "POSCAR", "POTCAR", "CONTCAR", "OUTCAR", "vasprun.xml"}

_vasp_files = set()
for v in VASP_RAW_DATA_ORG.values():
    _vasp_files.update(v)

VASP_RAW_DATA_ORG["input"].extend([f"{f}.orig" for f in VASP_INPUT_FILES])


def discover_vasp_files(
    target_dir: FSPathType,
) -> dict[str, list[FileMetadata]]:
    """
    Scan a target directory and identify VASP files.

    Parameters
    -----------
    target_dir : FSPathType

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
                vasp_files.append(FileMetadata(name=p.name, path=Path(p.path)))
    by_suffix = defaultdict(list)
    for file_meta in vasp_files:
        by_suffix[file_meta.calc_suffix].append(file_meta)
    return dict(by_suffix)  # type: ignore[arg-type]


def discover_and_sort_vasp_files(
    target_dir: FSPathType,
) -> dict[str, dict[str, Path | list[Path]]]:
    """
    Find and sort VASP files from a directory for TaskDoc.

    Parameters
    -----------
    target_dir : FSPathType

    Returns
    -----------
    dict of str (categories) to list of FileMetadata (list of VASP files in
        that category)
    """
    by_type: defaultdict[str, dict[str, Path | list[Path]]] = defaultdict(dict)
    for calc_suffix, files in discover_vasp_files(target_dir).items():
        for _f in files:
            f = _f.name.lower()
            file_path = _f.path.resolve()

            for k in ("vasprun", "contcar", "outcar", "potcar.spec"):
                if k in f:
                    by_type[calc_suffix][f"{k.replace('.','_')}_file"] = file_path
                    break
            else:
                # NB: the POT file needs the extra `"potcar" not in f` check to ensure that
                # POTCARs are not classed as volumetric files.
                if any(
                    vf.lower() in f and "potcar" not in f
                    for vf in VASP_VOLUMETRIC_FILES
                ):
                    if "volumetric_files" not in by_type[_f.calc_suffix]:
                        by_type[calc_suffix]["volumetric_files"] = []
                    by_type[calc_suffix]["volumetric_files"].append(file_path)  # type: ignore[union-attr]

                elif "poscar.t=" in f:
                    if "elph_poscars" not in by_type[calc_suffix]:
                        by_type[_f.calc_suffix]["elph_poscars"] = []

                    by_type[calc_suffix]["elph_poscars"].append(file_path)  # type: ignore[union-attr]

    return dict(by_type)


def recursive_discover_vasp_files(
    target_dir: FSPathType,
    only_valid: bool = False,
    max_depth: int | None = None,
) -> dict[CalculationLocator, list[FileMetadata]]:
    """
    Recursively scan a target directory and identify VASP files.

    Parameters
    -----------
    target_dir : FSPathType
    only_valid : bool = False (default)
        Whether to only include directories which have the required
        minimum number of input and output files for parsing.
    max_depth : non-negative int or None (default)
        If an int, the maximum depth with which directories are scanned
        for VASP files. For example, if max_depth == 1, this would only
        search `target_dir` and any immediate sub-directories in `target_dir`.

    Returns
    -----------
    dict of Path  to list of FileMetadata identified as VASP files.
    """

    head_dir = Path(target_dir).resolve()

    if max_depth and (max_depth < 0 or not isinstance(max_depth, int)):
        raise ValueError(
            "The maximum path depth should be a non-negative integer, "
            "with zero indicating that only the current directory should "
            "be searched."
        )

    def _path_depth_check(tpath: FSPathType) -> bool:
        if max_depth and (tp := Path(tpath).resolve()) != head_dir:
            for depth, parent in enumerate(tp.parents):
                if parent == head_dir:
                    break
            return depth + 1 <= max_depth
        return True

    def _recursive_discover_vasp_files(
        tdir: FSPathType, paths: dict[CalculationLocator, list[FileMetadata]]
    ) -> None:
        if Path(tdir).is_dir() and _path_depth_check(tdir):
            with os.scandir(tdir) as scan_dir:
                for p in scan_dir:
                    _recursive_discover_vasp_files(p, paths)

            if tpaths_by_suffix := discover_vasp_files(tdir):
                for calc_suffix, tpaths in tpaths_by_suffix.items():
                    # Check if minimum number of VASP files are present
                    # TODO: update with vaspout.h5 parsing
                    if only_valid and any(
                        not any(f in file.name for file in tpaths)
                        for f in REQUIRED_VASP_FILES
                    ):
                        # Incomplete calculation input/output
                        continue
                    paths[
                        CalculationLocator(
                            path=Path(tdir).resolve(), modifier=calc_suffix
                        )
                    ] = tpaths

    vasp_files: dict[CalculationLocator, list[FileMetadata]] = {}
    _recursive_discover_vasp_files(target_dir, vasp_files)
    return vasp_files
