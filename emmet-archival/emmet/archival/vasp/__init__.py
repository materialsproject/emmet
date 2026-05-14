"""Define common variables in the VASP sub-library."""

from __future__ import annotations

from emmet.core.io.pymatgen import (
    Incar,
    Kpoints,
    Poscar,
    Chgcar,
    Elfcar,
    Locpot,
    PotcarSummaryStats,
)

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
