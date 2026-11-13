"""Read what the OUTCAR of a VASP calculation has for every ionic step.

pymatgen's `Outcar` only has the magnetization of the last ionic step. VASP writes
the magnetic moments of the atoms (projected on the spheres of the PAW method, with
LORBIT >= 10 or RWIGS) after each ionic step, and the total magnetization of the cell
after each electronic step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from monty.io import zopen

if TYPE_CHECKING:
    from pathlib import Path

_FLOAT = re.compile(r"-?\d+\.\d+")
_BLOCKS = {
    "magnetization (x)": 0,
    "magnetization (y)": 1,
    "magnetization (z)": 2,
}
_END_OF_STEP = "FREE ENERGIE OF THE ION-ELECTRON SYSTEM"
_SITE_ROW = re.compile(r"^\d+(?:\s*-?\d+\.\d+)+$")
"""A row of a block of moments: the number of the atom, then numbers (`1  0.114  -0.001  0.000  0.114`).

The columns have a fixed width, so a large negative number has no space before it."""


@dataclass
class StepMagnetization:
    """The magnetization at the end of each ionic step of an OUTCAR.

    Both lists have an item for each ionic step, which is None where the OUTCAR
    has none: no moments are written for an unpolarized calculation, nor without
    LORBIT or RWIGS, and the total is written for any calculation with spin.
    """

    magmoms: list[np.ndarray | None] = field(default_factory=list)
    """The total (s + p + d + f) moment of each atom, in mu_B, `(sites,)` for a collinear
    calculation and `(sites, 3)` for a noncollinear one, with the x, y and z components."""
    total: list[np.ndarray | None] = field(default_factory=list)
    """The total magnetization of the cell, in mu_B: `(1,)` or `(3,)`."""

    @property
    def num_ionic_steps(self) -> int:
        return len(self.magmoms)


def read_step_magnetization(path: str | Path) -> StepMagnetization:
    """Read the magnetic moments and total magnetization after each ionic step of an OUTCAR.

    The OUTCAR is read once, a line at a time. The moments written after the last ionic
    step, and again at the end of the file, belong to no step and are not returned.

    Parameters
    -----------
    path : str or Path
        The OUTCAR, which can be compressed.

    Returns
    -----------
    StepMagnetization
        With an item for each ionic step of the OUTCAR, counted by the
        energies written after it.
    """
    result = StepMagnetization()
    components: dict[int, list[float]] = {}
    total: np.ndarray | None = None
    block: int | None = None

    with zopen(str(path), "rt") as file:
        for line in file:
            stripped = line.strip()
            if block is not None:
                if _SITE_ROW.match(stripped):
                    components[block].append(float(_FLOAT.findall(stripped)[-1]))
                    continue
                # Before the rows are a header and a line of dashes. After them is a line of
                # dashes and the sum of the atoms, but only if there is more than one atom, so
                # the block is over at the first line after its rows which is not one of them.
                before_rows = not components[block] and (
                    not stripped or stripped.startswith("#") or set(stripped) == {"-"}
                )
                if before_rows:
                    continue
                block = None
            if stripped in _BLOCKS:
                block = _BLOCKS[stripped]
                components[block] = []
            elif (
                stripped.startswith("number of electron")
                and "magnetization" in stripped
            ):
                # the first is the number of electrons
                values = _FLOAT.findall(stripped.split("magnetization", 1)[1])
                total = np.array(values, dtype=float) if values else None
            elif _END_OF_STEP in stripped:
                result.magmoms.append(_combine(components))
                result.total.append(total)
                components, total = {}, None
    return result


def _combine(components: dict[int, list[float]]) -> np.ndarray | None:
    """The moments of the atoms, from the blocks of the components that were read."""
    if not components or not all(components.values()):
        return None
    if set(components) == {0}:
        return np.asarray(components[0])
    if set(components) == {0, 1, 2} and len({len(v) for v in components.values()}) == 1:
        return np.stack([components[i] for i in range(3)], axis=-1)
    return None
