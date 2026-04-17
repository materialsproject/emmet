"""Define core atomistic data structures and analysis."""

from __future__ import annotations

from functools import cached_property
from math import gcd
from typing import Any, TYPE_CHECKING

import numpy as np
from pydantic import BaseModel

from emmet.core.atoms.elements import Element, ELEMENT_DATA
from emmet.core.math import Matrix3D, Vector3D

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self

    from pymatgen.core.sites import Site, PeriodicSite
    from pymatgen.core.structure import Molecule as PmgMolecule


class Site(BaseModel):
    """Schematize a site in a molecule or material."""

    element: Element
    cart_coords: Vector3D
    charge: float | None = None
    spin: float | None = None
    degrees_of_freedom: tuple[bool, bool, bool] | None = None
    velocity: Vector3D | None = None

    def __str__(self) -> str:
        base_name = f"{self.element.name}"
        if self.charge is not None:
            charge_sign = "+" if self.charge >= 0 else "-"
            if (abs_charge := abs(self.charge)) == 1:
                base_name += charge_sign
            else:
                if (abs_charge - round(abs_charge)) < 1e-6:
                    abs_charge = round(abs_charge)
                base_name += f"{abs_charge}{charge_sign}"
        return base_name

    @property
    def Z(self) -> int:
        return ELEMENT_DATA[self.element].Z

    @classmethod
    def from_pmg(cls, site: Site | PeriodicSite) -> Self:

        from pymatgen.core.periodic_table import Species

        if len(site.species.elements) > 1:
            raise ValueError("`Site` currently cannot represent a disordered site!")

        charge = None
        if isinstance(species := site.species.elements[0], Species):
            charge = species.oxi_state

        return cls(
            element=species.element.name,
            cart_coords=site.coords,
            charge=charge,
            spin=site.properties.get("magmom"),
            degrees_of_freedom=site.properties.get("selective_dynamics"),
            velocity=site.properties.get("velocities"),
        )

    def to_pmg(self, cell: Matrix3D | None = None) -> Site | PeriodicSite:

        from pymatgen.core.sites import Site, PeriodicSite

        if cell is not None:
            from pymatgen.core.lattice import Lattice

        species = {str(self): 1.0}
        properties = {
            v: getattr(self, k)
            for k, v in {
                "spin": "magmom",
                "degrees_of_freedom": "selective_dynamics",
                "velocity": "velocities",
            }.items()
        }
        for k in list(properties):
            if properties[k] is None:
                properties.pop(k)

        if cell is None:
            return Site(
                species,
                self.cart_coords,
                properties=properties,
            )

        return PeriodicSite(
            species,
            self.cart_coords,
            lattice=Lattice(cell),
            coords_are_cartesian=True,
            properties=properties,
        )


class Molecule(BaseModel):
    """Schematize a molecular structure."""

    sites: list[Site]

    def composition(self, include_charges: bool = True) -> dict[str, int]:
        comp = {
            str(site) if include_charges else site.element.name: 0
            for site in self.sites
        }
        for site in self.sites:
            comp[str(site)] += 1
        return comp

    def reduced_composition(self, include_charges: bool = True) -> dict[str, int]:
        base_comp = self.composition(include_charges=include_charges)
        factor = gcd(*base_comp.values())
        return {k: v // factor for k, v in base_comp.items()}

    @cached_property
    def mass(self) -> float:
        """Mass in atomic mass units."""
        return sum(ELEMENT_DATA[site.element].atomic_mass for site in self.sites)

    def _aggregate_site_properties(self, prop: str, default: Any = None) -> np.ndarray:
        return np.array([getattr(site, prop, None) or default for site in self.sites])

    def _sum_scalar_site_properties(self, prop: str, default: float = 0.0) -> float:
        return sum(getattr(site, prop, None) or default for site in self.sites)

    @cached_property
    def cart_coords(self) -> np.ndarray[float]:
        return self._aggregate_site_properties("cart_coords")

    @cached_property
    def charge(self) -> float:
        return self._sum_scalar_site_properties("charge")

    @cached_property
    def spin(self) -> float:
        return self._sum_scalar_site_properties("spin")

    @cached_property
    def spins(self) -> np.ndarray[float]:
        return self._aggregate_site_properties("spin")

    @cached_property
    def degrees_of_freedom(self) -> np.ndarray[bool]:
        return self._aggregate_site_properties(
            "degrees_of_freedom", default=(True, True, True)
        )

    @classmethod
    def from_pmg(cls, molecule: PmgMolecule) -> Self:
        return cls(
            sites=[Site.from_pmg(site) for site in molecule],
        )

    def to_pmg(self) -> PmgMolecule:
        from pymatgen.core.structure import Molecule as PmgMolecule

        return PmgMolecule.from_sites(
            [site.to_pmg(cell=self.cell) for site in self.sites]
        )
