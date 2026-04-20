"""Define core atomistic data structures and analysis."""

from __future__ import annotations

from functools import cached_property
from math import gcd
from typing import Any, TYPE_CHECKING

import numpy as np
from pydantic import BaseModel, model_validator

from emmet.core.atoms.elements import Element, ELEMENT_DATA, parse_species_str
from emmet.core.math import Matrix3D, Vector3D

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self

    from pymatgen.core.composition import Composition
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


class Compound(BaseModel):

    species: list[str]
    coefficients: list[int]

    @model_validator(mode="before")
    @classmethod
    def _reduce(cls, config) -> Self:

        if not all(config.get(k) for k in cls.model_fields) or len(
            config["species"]
        ) != len(config["coefficients"]):
            raise ValueError(f"Invalid input specified to {cls.__name__}.")

        base_config: dict[str, int] = {}
        for idx, spec in enumerate(config["species"]):
            if spec not in base_config:
                base_config[spec] = 0
            base_config[spec] += config["coefficients"][idx]
        sorted_species = sorted(base_config.keys())
        return {
            "species": sorted_species,
            "coefficients": [base_config[spec] for spec in sorted_species],
        }

    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            + ", ".join(
                f"{spec}: {self.coefficients[idx]}"
                for idx, spec in enumerate(self.species)
            )
            + ")"
        )

    def __repr__(self) -> str:
        return self.__str__()

    @cached_property
    def elements(self) -> list[Element]:
        return [parse_species_str(spec)[0] for spec in self.species]

    @classmethod
    def from_dict(cls, dct: dict[str, int]):
        ordered_species = sorted(dct.keys())
        return cls(
            species=ordered_species,
            coefficients=[dct[k] for k in ordered_species],
        )

    def to_dict(self) -> dict[str, int]:
        return dict(
            [(spec, self.coefficients[idx]) for idx, spec in enumerate(self.species)]
        )

    def to_pmg(self) -> Composition:
        from pymatgen.core.composition import Composition

        return Composition(self.to_dict())

    @property
    def reduced(self) -> Compound:
        factor = gcd(*self.coefficients)
        return Compound(
            species=self.species, coefficients=[v // factor for v in self.coefficients]
        )

    @cached_property
    def mass(self) -> float:
        """Mass in atomic mass units."""
        return sum(ELEMENT_DATA[ele].atomic_mass for ele in self.elements)

    def __getitem__(self, species: str) -> Any:
        """Return coefficient of species if present, otherwise raise an exception."""
        if species in self.species:
            return next(
                self.coefficients[idx]
                for idx, spec in enumerate(self.species)
                if spec == species
            )
        raise KeyError(species)

    def get(self, item: str, default: Any = None) -> Any:
        """Return a model field `item`, or `default` if it doesn't exist."""
        try:
            return self.__getitem__(item)
        except KeyError:
            return default


class Molecule(BaseModel):
    """Schematize a molecular structure."""

    sites: list[Site]

    def __len__(self) -> int:
        return len(self.sites)

    @property
    def num_sites(self) -> int:
        return len(self)

    @property
    def composition(self) -> Compound:
        return Compound(
            species=[str(site) for site in self.sites], coefficients=[1] * len(self)
        )

    @property
    def reduced_composition(self) -> Compound:
        return self.composition.reduced

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
