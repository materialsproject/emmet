"""Define data structures for periodic materials."""

from __future__ import annotations

from functools import cached_property
import re
from typing import TYPE_CHECKING

import numpy as np
from scipy.constants import atomic_mass
import spglib

from emmet.core.atoms.base import Molecule, Site
from emmet.core.atoms.elements import ELEMENT_DATA
from emmet.core.math import Matrix3D
from emmet.core.settings import EmmetSettings

if TYPE_CHECKING:
    from typing import Literal
    from typing_extensions import Self

    from pymatgen.core.structure import Structure

SETTINGS = EmmetSettings()


class Cell(np.ndarray):

    def __new__(cls, data, **kwargs):
        arr = np.asarray(data, dtype=float)
        return arr.view(cls)

    def __array_finalize__(self, obj):
        # If shape/dtype are wrong, demote to plain ndarray instead of raising
        if self.shape != (3, 3) or self.dtype != np.float64:
            # Can't mutate self's type in-place, so we flag it for __array_ufunc__
            self._invalid = True

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        # Delegate to plain ndarray, then re-wrap only if result is still 3x3 float
        plain_inputs = [np.asarray(x) for x in inputs]
        result = getattr(ufunc, method)(*plain_inputs, **kwargs)
        if (
            isinstance(result, np.ndarray)
            and result.shape == (3, 3)
            and result.dtype == np.float64
        ):
            return result.view(Cell)
        return result  # return plain ndarray if result doesn't qualify

    @cached_property
    def volume(self) -> float:
        return abs(np.linalg.det(self))

    @cached_property
    def _reciprocal(self) -> Self:
        return Cell(
            np.array([np.cross(self[(i + 1) % 3], self[(i + 2) % 3]) for i in range(3)])
            / self.volume
        )

    @property
    def reciprocal(self) -> Self:
        return 2 * np.pi * self._reciprocal

    @cached_property
    def _vector_norms(self) -> np.ndarray[float]:
        return np.linalg.norm(self, axis=1)

    @cached_property
    def _angles(self) -> np.ndarray:
        return [
            180
            / np.pi
            * np.arccos(
                np.dot(self.matrix[i], self.matrix[(i + 1) % 3])
                / (self._vector_norms[i] * self._vector_norms[(i + 1) % 3])
            )
            for i in range(3)
        ]

    @property
    def a(self) -> float:
        return self._vector_norms[0]

    @property
    def b(self) -> float:
        return self._vector_norms[1]

    @property
    def c(self) -> float:
        return self._vector_norms[2]

    @property
    def alpha(self) -> float:
        return self._angles[1]

    @property
    def beta(self) -> float:
        return self._angles[2]

    @property
    def gamma(self) -> float:
        return self._angles[0]

    @staticmethod
    def _get_coords(
        cell: Cell, coords: np.ndarray, to: Literal["cartesian", "direct"]
    ) -> np.ndarray[float]:
        if to == "direct":
            return np.einsum("ij,ki->kj", cell._reciprocal.T, coords)
        elif to == "cartesian":
            return np.einsum("ij,ki->kj", cell, coords)
        raise ValueError(
            f'Unknown transformation {to}. Please select "cartesian" or "direct".'
        )

    def get_coords(
        self, coords: np.ndarray, to: Literal["cartesian", "direct"]
    ) -> np.ndarray[float]:
        return self._get_coords(self, coords, to=to)


class Material(Molecule):
    """Schematize an ordered material crystal structure."""

    lattice: Matrix3D

    @cached_property
    def cell(self) -> Cell:
        return Cell(self.lattice)

    @property
    def volume(self) -> float:
        return self.cell.volume

    @cached_property
    def frac_coords(self) -> np.ndarray[float]:
        return self.cell.get_coords(self.cart_coords, to="direct")

    def density_g_cm3(self) -> float:
        """Get density of material in g/cm^3."""
        return self.composition.mass * atomic_mass * 1e27 / self.cell.volume

    @classmethod
    def from_pmg(cls, structure: Structure) -> Self:
        return cls(
            lattice=structure.lattice.matrix,
            sites=[Site.from_pmg(site) for site in structure],
        )

    def to_pmg(self) -> Structure:
        from pymatgen.core.structure import Structure

        return Structure.from_sites(
            [site.to_pmg(cell=self.cell) for site in self.sites]
        )

    @cached_property
    def _to_spglib(self) -> tuple[Cell, np.ndarray[float], np.ndarray[int]]:
        """Create an spglib-compatible representation of the atoms."""
        return (
            self.cell,
            self.frac_coords,
            [site.Z for site in self.sites],
        )

    @classmethod
    def _from_spglib(
        cls, spglib_rep: tuple[Matrix3D, np.ndarray[float], np.ndarray[int]]
    ) -> Self:
        cell, frac_coords, atomic_numbers = spglib_rep

        zmap = {
            z: next(ele for ele, data in ELEMENT_DATA.items() if data.Z == z)
            for z in set(atomic_numbers)
        }
        cart_coords = Cell(cell).get_coords(frac_coords, to="cartesian")
        return cls(
            lattice=cell,
            sites=[
                Site(
                    element=zmap[z],
                    cart_coords=cart_coords[idx],
                )
                for idx, z in enumerate(atomic_numbers)
            ],
        )

    def primitive(
        self, symprec: float = SETTINGS.SYMPREC, angle_tol: float = SETTINGS.ANGLE_TOL
    ) -> Material:
        return self._from_spglib(
            spglib.find_primitive(
                self._to_spglib,
                symprec=symprec,
                angle_tolerance=angle_tol,
            )
        )

    def conventional(
        self, symprec: float = SETTINGS.SYMPREC, angle_tol: float = SETTINGS.ANGLE_TOL
    ) -> Material:
        return self._from_spglib(
            spglib.standardize_cell(
                self._to_spglib, symprec=symprec, angle_tol=angle_tol
            )
        )

    def get_space_group_info(
        self, symprec: float = SETTINGS.SYMPREC, angle_tol: float = SETTINGS.ANGLE_TOL
    ) -> tuple[str, int]:
        sg_info = spglib.get_spacegroup(
            self._to_spglib, symprec=symprec, angle_tolerance=angle_tol
        )
        return tuple(re.match(r"(.*) \((.*)\)", sg_info).groups())
