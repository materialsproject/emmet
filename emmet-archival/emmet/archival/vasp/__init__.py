"""Define common variables in the VASP sub-library."""
from __future__ import annotations
import json
from pathlib import Path

from pymatgen.io.vasp.inputs import Incar, Kpoints, Poscar, Potcar
from pymatgen.io.vasp.outputs import Chgcar, Elfcar, Locpot


VASP_INPUT_FILES = [
    "INCAR",
    "KPOINTS",
    "KPOINTS_OPT",
    "POSCAR",
    "POTCAR",
    "POTCAR.spec",
]
VASP_ELECTRONIC_STRUCTURE = [
    "EIGENVAL",
    "DOSCAR",
]
VASP_VOLUMETRIC_FILES = (
    ["CHGCAR"] + [f"AECCAR{i}" for i in range(3)] + ["ELFCAR", "LOCPOT"]
)
VASP_OUTPUT_FILES = ["CONTCAR", "OSZICAR", "OUTCAR", "vasprun.xml", "vaspout.h5"]

VASP_RAW_DATA_ORG = {
    "input": VASP_INPUT_FILES.copy(),
    "output": VASP_OUTPUT_FILES.copy(),
    "volumetric": VASP_VOLUMETRIC_FILES.copy(),
    "electronic_structure": VASP_ELECTRONIC_STRUCTURE.copy(),
    "workflow": ["FW.json", "custodian.json", "transformations.json"],
}

for f in VASP_INPUT_FILES:
    fspec = f.split(".")
    new_f = fspec[0] + ".orig"
    if len(fspec) > 1:
        new_f += "." + ".".join(fspec[1:])
    VASP_RAW_DATA_ORG["input"].append(new_f)


class PotcarSpec:
    """Store high-level POTCAR information without licensed data.

    Needed to avoid storage of full POTCARs and be compliant
    with terms of POTCAR licensing.
    """

    def __init__(self, potcar: Potcar):
        self.spec = [p._summary_stats for p in potcar]

    @classmethod
    def from_file(cls, file_path: str | Path):
        """Create a PotcarSpec from a file.

        Parameters
        -----------
        file_path : str or Path
            The path to the POTCAR file.

        Returns
        -----------
        A PotcarSpec of the specified POTCAR.
        """
        return cls(Potcar.from_file(file_path))

    def __str__(self) -> str:
        """Define str representation when writing to RawArchive."""
        return json.dumps(self.spec)


PMG_OBJ = {
    "INCAR": Incar,
    "KPOINTS": Kpoints,
    "KPOINTS_OPT": Kpoints,
    "POSCAR": Poscar,
    "POTCAR": PotcarSpec,
    "CHGCAR": Chgcar,
    "AECCAR0": Chgcar,
    "AECCAR1": Chgcar,
    "AECCAR2": Chgcar,
    "ELFCAR": Elfcar,
    "LOCPOT": Locpot,
}
