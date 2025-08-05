"""Define common variables in the VASP sub-library."""

from __future__ import annotations

from pymatgen.io.vasp.inputs import Incar, Kpoints, Poscar
from pymatgen.io.vasp.outputs import Chgcar, Elfcar, Locpot

from pymatgen.io.validation.common import PotcarSummaryStats

PMG_OBJ = {
    "INCAR": Incar,
    "KPOINTS": Kpoints,
    "KPOINTS_OPT": Kpoints,
    "POSCAR": Poscar,
    "POTCAR": PotcarSummaryStats,
    "CHGCAR": Chgcar,
    "AECCAR0": Chgcar,
    "AECCAR1": Chgcar,
    "AECCAR2": Chgcar,
    "ELFCAR": Elfcar,
    "LOCPOT": Locpot,
    "POT": Chgcar,  # this includes augmentation data
}
