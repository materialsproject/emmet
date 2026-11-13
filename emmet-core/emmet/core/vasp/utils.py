"""Define utilities needed for parsing VASP calculations."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from pydantic import BaseModel, Field, model_validator

from emmet.core.utils import get_hash_blocked
from emmet.core.vasp.models import volumetric_file_type

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from emmet.core.types.typing import FSPathType

logger = logging.getLogger(__name__)

TASK_NAMES = {"precondition"} | {f"relax{i+1}" for i in range(9)}

DEFAULT_CALC_SUFFIXES: tuple[str, ...] = (
    "precondition",
    *(f"relax{i + 1}" for i in range(9)),
    "static",
)
"""The suffixes of the calculations in a multi-calculation directory.

The order matters: it is the order in which the calculations were run. The
first calculation is the one which `.orig` input files describe, and the last
calculation is the one which unsuffixed output files belong to.
"""

COMPRESSION_EXTENSIONS: tuple[str, ...] = (".gz", ".bz2", ".xz", ".zst", ".lzma", ".Z")
"""Extensions of compressed files, which are ignored when identifying VASP files."""

PARCHG_ALL_PARTS: tuple[str, ...] = ("ALLB", "ALLK")
"""Parts of the names of PARCHG files, e.g., PARCHG.ALLB.0002, which stand for all bands / k-points."""

STANDARD_CALC_SUFFIX = "standard"
"""The suffix of a calculation whose files have no calculation suffix."""


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
        "PARCHG",
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


_FILE_TYPE_CATEGORIES: dict[str, str] = {
    file_type: category
    for category, file_types in (
        ("input", VASP_INPUT_FILES),
        ("output", VASP_OUTPUT_FILES),
        ("electronic_structure", VASP_ELECTRONIC_STRUCTURE),
        ("workflow", ["FW.json", "custodian.json", "transformations.json"]),
    )
    for file_type in file_types
}
"""Category of each known (non-volumetric) VASP file type, by its canonical name."""


class VaspFileName(NamedTuple):
    """The parts of the name of a VASP file, see `parse_vasp_file_name`."""

    file_type: str
    """Canonical name of the type of file, e.g., INCAR, POTCAR.spec, vasprun.xml,
    CHGCAR. Electron-phonon POSCARs (POSCAR.T=300) are of type POSCAR.T"""

    category: str
    """One of the keys of `VASP_RAW_DATA_ORG` that is not a suffix:
    input, output, volumetric, electronic_structure, workflow."""

    calc_suffix: str | None
    """The calculation suffix, if the name has one of the suffixes searched for."""

    is_orig: bool
    """Whether the file is an original, pre-correction copy, e.g., INCAR.orig."""

    unrecognized: tuple[str, ...] = ()
    """Parts of the name which were not understood, e.g., an unknown calculation suffix."""


def parse_vasp_file_name(
    file_name: str | os.PathLike,
    suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
) -> VaspFileName | None:
    """Identify a VASP file from its name.

    The name must start with the exact name of a VASP file, followed
    by any of: a calculation suffix, `orig`, and a compression extension.
    For example: `INCAR`, `INCAR.orig.relax1`, `vasprun.xml.relax1.gz`,
    `POTCAR.spec`, `CHGCAR.relax2.gz`, `POSCAR.T=300.gz`.

    Because the name of the file has to match exactly, `PARCHG` is not mistaken
    for `CHG`, `POTCAR` for `POT`, or `my_vasprun.xml` for a vasprun.xml.

    Other dot-separated parts of the name which are not recognized, such as an
    unknown calculation suffix, do not stop the file from being identified,
    but are returned in `unrecognized`. The indices of PARCHG files, e.g.,
    `PARCHG.0001.0002`, `PARCHG.0001.ALLK` and `PARCHG.ALLB.0002`, are understood.

    Parameters
    -----------
    file_name : str or PathLike
        The name of the file. Any parent directories are ignored.
    suffixes : sequence of str
        The calculation suffixes to look for.

    Returns
    -----------
    VaspFileName or None
        None if the file is not a VASP file.
    """
    name = Path(file_name).name
    while name.endswith(COMPRESSION_EXTENSIONS):
        name = name.rsplit(".", 1)[0]
    parts = name.split(".")

    file_type: str | None = None
    rest = parts[1:]
    if len(parts) > 1 and f"{parts[0]}.{parts[1]}" in _FILE_TYPE_CATEGORIES:
        # e.g., vasprun.xml, POTCAR.spec
        file_type = f"{parts[0]}.{parts[1]}"
        rest = parts[2:]
        category = _FILE_TYPE_CATEGORIES[file_type]
    elif parts[0] in _FILE_TYPE_CATEGORIES:
        file_type = parts[0]
        category = _FILE_TYPE_CATEGORIES[file_type]
    elif vol_type := volumetric_file_type(parts[0]):
        file_type = vol_type
        category = "volumetric"
    else:
        return None

    calc_suffix = None
    is_orig = False
    unrecognized = []
    for part in rest:
        if part == "orig":
            is_orig = True
        elif part in suffixes:
            calc_suffix = part
        elif file_type == "POSCAR" and part.startswith("T="):
            # POSCARs displaced for electron-phonon coupling
            file_type = "POSCAR.T"
        elif file_type == "PARCHG" and (part.isdigit() or part in PARCHG_ALL_PARTS):
            # band and k-point indices of partial charge densities, or ALLB / ALLK
            # for the sum over all selected bands / k-points
            continue
        else:
            unrecognized.append(part)

    return VaspFileName(file_type, category, calc_suffix, is_orig, tuple(unrecognized))


def check_vasp_file_name(
    file_name: str | os.PathLike,
    suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
) -> VaspFileName:
    """Identify a VASP file from its name, raising if it cannot be assigned.

    Unlike `parse_vasp_file_name`, this does not accept names with parts which
    are not understood. Such a file is a VASP file, but it is unknown which
    calculation it is for, or whether it is an output at all. For example,
    `vasprun.xml.relax10.gz` (unknown suffix) or `CHGCAR.bak`.

    Use this where a file was selected on purpose, e.g., when a user adds it
    to a submission, instead of discovered, in which case it is skipped.

    Parameters
    -----------
    file_name : str or PathLike
        The name of the file. Any parent directories are ignored.
    suffixes : sequence of str
        The calculation suffixes which are allowed.

    Returns
    -----------
    VaspFileName

    Raises
    -----------
    ValueError
        If the file is not a VASP file, or its name has unrecognized parts.
    """
    name = Path(file_name).name
    if (parsed := parse_vasp_file_name(name, suffixes)) is None:
        raise ValueError(f"{name} is not a recognized VASP file.")
    if parsed.unrecognized:
        raise ValueError(
            f"{name}: unrecognized part(s) of the file name "
            f"{', '.join(repr(p) for p in parsed.unrecognized)}. The file cannot be "
            f"assigned to a calculation. The calculation suffixes are "
            f"{', '.join(suffixes)}. Rename the file, or leave it out."
        )
    return parsed


def discover_vasp_files(
    target_dir: FSPathType,
) -> dict[str, list[FileMetadata]]:
    """
    Scan a target directory and identify VASP files.

    Files are identified by name, see `parse_vasp_file_name`.

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
            if p.is_file() and parse_vasp_file_name(p.name) is not None:
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

    This only looks at the files in `target_dir` itself, and does not
    share files between calculations. To discover the calculations in
    a directory in any of its layouts, use `discover_calculations`.

    Parameters
    -----------
    target_dir : FSPathType

    Returns
    -----------
    dict of str (categories) to list of FileMetadata (list of VASP files in
        that category)
    """
    role_keys = {
        "vasprun.xml": "vasprun_file",
        "CONTCAR": "contcar_file",
        "OUTCAR": "outcar_file",
        "POTCAR.spec": "potcar_spec_file",
        "OSZICAR": "oszicar_file",
    }
    by_type: defaultdict[str, dict[str, Path | list[Path]]] = defaultdict(dict)
    for calc_suffix, files in discover_vasp_files(target_dir).items():
        for _f in files:
            parsed = parse_vasp_file_name(_f.name)
            if parsed is None or parsed.is_orig:
                continue
            file_path = _f.path.resolve()

            if parsed.file_type in role_keys:
                by_type[calc_suffix][role_keys[parsed.file_type]] = file_path
            elif parsed.category == "volumetric":
                by_type[calc_suffix].setdefault("volumetric_files", []).append(  # type: ignore[union-attr]
                    file_path
                )
            elif parsed.file_type == "POSCAR.T":
                by_type[calc_suffix].setdefault("elph_poscars", []).append(  # type: ignore[union-attr]
                    file_path
                )

    return dict(by_type)


class CalculationFiles(BaseModel):
    """The files of a single VASP calculation.

    Files are keyed by their canonical type (see `parse_vasp_file_name`), and
    a calculation has at most one file of each type.
    """

    calc_suffix: str = Field(
        STANDARD_CALC_SUFFIX,
        description="The suffix of the calculation, e.g., relax1, or "
        "standard if the files have no suffix.",
    )
    directory: Path = Field(description="The directory the calculation's files are in.")
    is_first: bool = Field(
        True,
        description="Whether this is the first calculation of its directory.",
    )
    is_last: bool = Field(
        True,
        description="Whether this is the last calculation of its directory.",
    )
    inputs: dict[str, Path] = Field(
        {}, description="Input files: INCAR, KPOINTS, POSCAR, POTCAR, POTCAR.spec."
    )
    orig_inputs: dict[str, Path] = Field(
        {},
        description="Original (pre-correction) input files, e.g., INCAR.orig. A "
        "directory with multiple calculations has one set of these, which are "
        "given to the first calculation, as they are the inputs of the first "
        "calculation. Explicitly suffixed ones (INCAR.orig.relax2) are an "
        "exception, and are given to the calculation they are suffixed with.",
    )
    outputs: dict[str, Path] = Field(
        {}, description="Output files: vasprun.xml, OUTCAR, CONTCAR, OSZICAR, etc."
    )
    volumetric: dict[str, Path] = Field(
        {}, description="Volumetric files: CHGCAR, LOCPOT, AECCAR0, etc."
    )
    electronic_structure: dict[str, Path] = Field(
        {}, description="Electronic structure files: DOSCAR, EIGENVAL."
    )
    elph_poscars: list[Path] = Field(
        [], description="Electron-phonon coupling displaced POSCARs."
    )
    extra_parchg: list[Path] = Field(
        [],
        description="PARCHG files which share their type with another PARCHG of the "
        "calculation, e.g., PARCHG.0001.0002 and PARCHG.0001.0003. `volumetric` "
        "has one of them, so that every file of the calculation is accounted for "
        "(see `file_paths`).",
    )
    workflow: dict[str, Path] = Field(
        {},
        description="Workflow files: custodian.json, transformations.json, FW.json. "
        "These describe the whole directory, and are given to every calculation in it.",
    )

    @property
    def vasprun(self) -> Path | None:
        return self.outputs.get("vasprun.xml")

    @property
    def outcar(self) -> Path | None:
        return self.outputs.get("OUTCAR")

    @property
    def contcar(self) -> Path | None:
        return self.outputs.get("CONTCAR")

    @property
    def oszicar(self) -> Path | None:
        return self.outputs.get("OSZICAR")

    @property
    def potcar_spec(self) -> Path | None:
        return self.inputs.get("POTCAR.spec")

    def to_calculation_kwargs(
        self, resolve: bool = True
    ) -> dict[str, Path | list[Path]]:
        """Get the file arguments of `Calculation.from_vasp_files`.

        Only the files which are present are included.

        Parameters
        -----------
        resolve : bool = True
            Whether to resolve symlinks in the file paths.
        """

        def _path(p: Path) -> Path:
            return p.resolve() if resolve else p

        kwargs: dict[str, Path | list[Path]] = {}
        for key, path in (
            ("vasprun_file", self.vasprun),
            ("outcar_file", self.outcar),
            ("contcar_file", self.contcar),
            ("oszicar_file", self.oszicar),
            ("potcar_spec_file", self.potcar_spec),
        ):
            if path is not None:
                kwargs[key] = _path(path)
        if self.volumetric:
            kwargs["volumetric_files"] = [_path(p) for p in self.volumetric.values()]
        if self.elph_poscars:
            kwargs["elph_poscars"] = [_path(p) for p in self.elph_poscars]
        return kwargs

    def file_paths(self) -> list[Path]:
        """Every file of the calculation, including shared files, without duplicates."""
        paths: dict[Path, None] = {}
        for group in (
            self.inputs,
            self.orig_inputs,
            self.outputs,
            self.volumetric,
            self.electronic_structure,
            self.workflow,
        ):
            paths.update(dict.fromkeys(group.values()))
        paths.update(dict.fromkeys(self.extra_parchg))
        paths.update(dict.fromkeys(self.elph_poscars))
        return list(paths)

    def _add(self, path: Path, parsed: VaspFileName) -> None:
        """Add a file of this calculation."""
        if parsed.is_orig:
            if parsed.category == "input":
                self.orig_inputs[parsed.file_type] = path
        elif parsed.file_type == "POSCAR.T":
            self.elph_poscars.append(path)
        elif parsed.category == "input":
            self.inputs[parsed.file_type] = path
        elif parsed.category == "output":
            self.outputs[parsed.file_type] = path
        elif parsed.category == "volumetric":
            if parsed.file_type == "PARCHG" and "PARCHG" in self.volumetric:
                self.extra_parchg.append(self.volumetric["PARCHG"])
            self.volumetric[parsed.file_type] = path
        elif parsed.category == "electronic_structure":
            self.electronic_structure[parsed.file_type] = path
        elif parsed.category == "workflow":
            self.workflow[parsed.file_type] = path


def _scan_vasp_files(
    directory: Path, suffixes: Sequence[str]
) -> list[tuple[Path, VaspFileName]]:
    """Find the VASP files in a directory, sorted by name.

    Files with parts of their name which are not understood, e.g., a suffix which
    is not in `suffixes`, are skipped: it is unknown which calculation they are for.
    """
    found = []
    with os.scandir(directory) as scan_dir:
        for p in scan_dir:
            if not p.is_file() or not (
                parsed := parse_vasp_file_name(p.name, suffixes)
            ):
                continue
            if parsed.unrecognized:
                logger.warning(
                    f"Ignoring {p.path}: unrecognized parts of file name "
                    f"{parsed.unrecognized}, calculation suffixes are {tuple(suffixes)}"
                )
                continue
            found.append((Path(p.path), parsed))
    return sorted(found, key=lambda x: x[0].name)


def discover_calculations(
    target_dir: FSPathType,
    suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
    require_vasprun: bool = True,
) -> dict[CalculationLocator, CalculationFiles]:
    """Find the calculations in a directory, and the files of each.

    A directory can have any of the following layouts:

    - One calculation, whose files have no suffix: `INCAR`, `vasprun.xml.gz`
    - Several calculations, whose files are distinguished by suffixes:
        `vasprun.xml.relax1.gz`, `vasprun.xml.relax2.gz`
    - Several calculations, each in a subdirectory named after its suffix:
        `relax1/vasprun.xml.gz`, `relax2/vasprun.xml.gz`

    A suffix is only searched for as a subdirectory if there are no
    files with that suffix in `target_dir`.

    Files with parts of their name which are not understood, such as an unknown
    suffix, are ignored, instead of being taken to have no suffix.

    Only calculations with a vasprun.xml are returned. A calculation is located by
    its directory, and a modifier: its suffix, or `standard` if it has none.
    Calculations in subdirectories are located by `target_dir`, and not the
    subdirectory, so that the calculations of a directory share a location.

    Files which are not specific to a calculation are shared:

    - Files with no suffix: POTCAR and POTCAR.spec are given to every
        calculation which has none of its own. Other unsuffixed files are
        given to the last calculation, if it has none of its own.
    - Original inputs with no suffix, e.g., INCAR.orig, are given to the first
        calculation.
    - Workflow files, e.g., custodian.json, are given to every calculation.

    Parameters
    -----------
    target_dir : FSPathType
        The directory.
    suffixes : sequence of str
        The suffixes of the calculations, in the order that the calculations
        were run, not in alphabetical order. The default is the known suffixes
        `DEFAULT_CALC_SUFFIXES`.
    require_vasprun : bool = True
        Whether a calculation needs a vasprun.xml to be returned. If False,
        calculations which have not been run, or did not finish, are returned
        too: any with input, output, volumetric or electronic structure files.
        Files with no suffix are then a calculation of their own only if
        there are no calculations with suffixes. Otherwise they are shared
        as described above.

    Returns
    -----------
    dict of CalculationLocator to CalculationFiles
        The calculations, in the order in which they were run, with
        calculations without a suffix last.
    """
    base_dir = Path(target_dir).resolve()
    suffixes = tuple(s for s in dict.fromkeys(suffixes) if s != STANDARD_CALC_SUFFIX)

    def is_calculation(calc_files: CalculationFiles) -> bool:
        if require_vasprun:
            return calc_files.vasprun is not None
        return bool(
            calc_files.inputs
            or calc_files.outputs
            or calc_files.volumetric
            or calc_files.electronic_structure
        )

    files: dict[str, CalculationFiles] = {}
    for path, parsed in _scan_vasp_files(base_dir, suffixes):
        suffix = parsed.calc_suffix or STANDARD_CALC_SUFFIX
        if suffix not in files:
            files[suffix] = CalculationFiles(calc_suffix=suffix, directory=base_dir)
        files[suffix]._add(path, parsed)

    for suffix in suffixes:
        if suffix not in files and (sub_dir := base_dir / suffix).is_dir():
            sub_files = CalculationFiles(calc_suffix=suffix, directory=sub_dir)
            for path, parsed in _scan_vasp_files(sub_dir, suffixes):
                sub_files._add(path, parsed)
            if is_calculation(sub_files):
                files[suffix] = sub_files

    order = [s for s in suffixes if s in files and is_calculation(files[s])]
    unsuffixed = files.get(STANDARD_CALC_SUFFIX)
    unsuffixed_is_calc = unsuffixed is not None and (
        unsuffixed.vasprun is not None
        if require_vasprun
        else (not order and is_calculation(unsuffixed))
    )
    if unsuffixed_is_calc:
        order.append(STANDARD_CALC_SUFFIX)
    if not order:
        return {}

    first, last = order[0], order[-1]
    if unsuffixed is not None:
        for file_type, path in unsuffixed.orig_inputs.items():
            files[first].orig_inputs.setdefault(file_type, path)
        if unsuffixed_is_calc and first != STANDARD_CALC_SUFFIX:
            unsuffixed.orig_inputs = {}

        for file_type in ("POTCAR", "POTCAR.spec"):
            if file_type in unsuffixed.inputs:
                for suffix in order:
                    files[suffix].inputs.setdefault(
                        file_type, unsuffixed.inputs[file_type]
                    )

        for suffix in order:
            for file_type, path in unsuffixed.workflow.items():
                files[suffix].workflow.setdefault(file_type, path)

        if not unsuffixed_is_calc:
            last_files = files[last]
            for group in ("inputs", "outputs", "volumetric", "electronic_structure"):
                for file_type, path in getattr(unsuffixed, group).items():
                    if group == "inputs" and file_type in ("POTCAR", "POTCAR.spec"):
                        continue
                    getattr(last_files, group).setdefault(file_type, path)
            if not last_files.elph_poscars:
                last_files.elph_poscars = list(unsuffixed.elph_poscars)
            if (
                not last_files.extra_parchg
                and "PARCHG" in unsuffixed.volumetric
                and last_files.volumetric.get("PARCHG")
                == unsuffixed.volumetric["PARCHG"]
            ):
                last_files.extra_parchg = list(unsuffixed.extra_parchg)

    for i, suffix in enumerate(order):
        files[suffix].is_first = i == 0
        files[suffix].is_last = i == len(order) - 1

    return {
        CalculationLocator(path=base_dir, modifier=suffix): files[suffix]
        for suffix in order
    }


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


def recursive_discover_calculations(
    target_dir: FSPathType,
    suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
    require_vasprun: bool = True,
    max_depth: int | None = None,
) -> dict[CalculationLocator, CalculationFiles]:
    """Find the calculations in a directory and all of its subdirectories.

    The calculations of every directory are found with `discover_calculations`.
    A subdirectory which holds the files of a calculation, like `relax1/`
    in a directory with the layout `relax1/vasprun.xml.gz`, is a part of its
    parent's calculations, and not searched for others. Any other subdirectory
    is searched, including those of directories which have calculations.

    Parameters
    -----------
    target_dir : FSPathType
        The directory to search in.
    suffixes : sequence of str
        The suffixes of the calculations, see `discover_calculations`.
    require_vasprun : bool = True
        Whether a calculation needs a vasprun.xml, see `discover_calculations`.
    max_depth : non-negative int or None (default)
        If an int, the maximum depth of the directories which are searched.
        With 1, `target_dir` and its immediate subdirectories are searched.

    Returns
    -----------
    dict of CalculationLocator to CalculationFiles
    """
    head_dir = Path(target_dir).resolve()
    if max_depth is not None and (
        not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth < 0
    ):
        raise ValueError(
            "The maximum path depth should be a non-negative integer, "
            "with zero indicating that only the current directory should "
            "be searched."
        )

    calculations: dict[CalculationLocator, CalculationFiles] = {}

    def _search(directory: Path, depth: int) -> None:
        found = discover_calculations(directory, suffixes, require_vasprun)
        calculations.update(found)
        if max_depth is not None and depth >= max_depth:
            return
        used = {calc_files.directory for calc_files in found.values()}
        with os.scandir(directory) as scan_dir:
            sub_dirs = sorted(
                (Path(p.path) for p in scan_dir if p.is_dir(follow_symlinks=False)),
                key=lambda p: p.name,
            )
        for sub_dir in sub_dirs:
            if sub_dir not in used:
                _search(sub_dir, depth + 1)

    _search(head_dir, 0)
    return calculations
