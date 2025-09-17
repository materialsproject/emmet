"""Define basic schema for band theoretic properties."""

from __future__ import annotations

import numbers
from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel, Field, computed_field, field_validator
from pymatgen.core import Lattice
from pymatgen.electronic_structure.bandstructure import (
    BandStructure as PmgBandStructure,
)
from pymatgen.electronic_structure.bandstructure import Kpoint
from pymatgen.electronic_structure.core import Orbital, Spin
from pymatgen.electronic_structure.dos import CompleteDos, Dos

from emmet.core.math import Matrix3D, Vector3D
from emmet.core.types.pymatgen_types.structure_adapter import StructureType

if TYPE_CHECKING:

    from pymatgen.core.sites import PeriodicSite
    from typing_extensions import Self

BAND_GAP_TOL = 1e-4


class BandTheoryBase(BaseModel):

    identifier: str | None = Field(None, description="The identifier of this object.")
    structure: StructureType | None = Field(
        None, description="The structure associated with this calculation."
    )


class BandStructure(
    BandTheoryBase, populate_by_name=True, validate_by_alias=True, validate_by_name=True
):
    """Define the schema of band structures.

    This class is generic enough to accommodate both
    electronic and phonon band structures.
    """

    qpoints: list[Vector3D] = Field(
        description="The wave vectors (q-points) at which the band structure was sampled, in direct coordinates.",
    )

    reciprocal_lattice: Matrix3D = Field(
        description="The reciprocal lattice.", validation_alias="lattice_rec"
    )

    labels_dict: dict[str, Vector3D] = Field(
        {}, description="The high-symmetry labels of specific q-points."
    )

    @field_validator("reciprocal_lattice", mode="before")
    def reciprocal_lattice_deserializer(cls, reciprocal_lattice):
        if isinstance(reciprocal_lattice, dict):
            return reciprocal_lattice.get("matrix")

        return reciprocal_lattice


class ElectronicBS(BandStructure):
    """Define an electronic band structure schema."""

    efermi: float = Field(
        description="The Fermi level (highest occupied energy level.)"
    )

    band_gap: float | None = Field(None, description="The value of the band gap.")

    spin_up_bands: list[list[float]] | None = Field(
        None,
        description="The eigen-energies of the spin-up electrons. The first index represents the band, the second the k-point index.",
    )

    spin_down_bands: list[list[float]] | None = Field(
        None,
        description="The eigen-energies of the spin-down electrons. The first index represents the band, the second the k-point index.",
    )

    is_direct: bool | None = Field(
        None, description="If the bandgap is non-zero, whether the band gap is direct."
    )

    spin_up_projections: list[list[list[list[float]]]] | None = Field(
        None,
        description=(
            "The atom-projected eigen-energies of the spin-up electrons. "
            "The first index is the band index. The second index is the k-point index. "
            "The third index is the site index. The final index is the orbital character, "
            "ordered as s, py, pz, px, dxy, dyz, dz2, dxz, dx2-y2,..."
        ),
    )

    spin_down_projections: list[list[list[list[float]]]] | None = Field(
        None,
        description=(
            "The atom-projected eigen-energies of the spin-down electrons. "
            "The first index is the band index. The second index is the k-point index. "
            "The third index is the site index. The final index is the orbital character, "
            "ordered as s, py, pz, px, dxy, dyz, dz2, dxz, dx2-y2,..."
        ),
    )

    @computed_field
    def is_metal(self) -> bool:
        """Whether the band gap is almost zero."""
        return (
            self.band_gap < BAND_GAP_TOL
            if isinstance(self.band_gap, numbers.Number)
            else False
        )

    @classmethod
    def from_pmg(cls, ebs: PmgBandStructure) -> Self:
        """Construct from a pymatgen band structure object."""
        band_gap_meta = ebs.get_band_gap()
        config = {
            "qpoints": [qpt.frac_coords for qpt in ebs.kpoints],
            "lattice_rec": ebs.lattice_rec.matrix,
            "efermi": ebs.efermi,
            "labels_dict": {
                label: qpt.frac_coords for label, qpt in ebs.labels_dict.items()
            },
            "structure": ebs.structure,
            "is_metal": ebs.is_metal(),
            "is_direct": band_gap_meta["direct"],
            "band_gap": band_gap_meta["energy"],
        }

        for spin in Spin:
            config[f"spin_{spin.name}_bands"] = ebs.bands.get(spin)
            if ebs.projections is not None:
                config[f"spin_{spin.name}_projections"] = ebs.projections.get(spin)
        return cls(**config)

    def to_pmg(
        self,
    ) -> PmgBandStructure:
        """Construct the pymatgen object from the current instance."""
        rlatt = Lattice(self.reciprocal_lattice)

        bands = {}
        projections = {}
        for spin in Spin:
            if v := getattr(self, f"spin_{spin.name}_bands", None):
                bands[spin] = np.array(v)
            if v := getattr(self, f"spin_{spin.name}_projections", None):
                projections[spin] = np.array(v)

        return PmgBandStructure(
            [Kpoint(q, lattice=rlatt).frac_coords for q in self.qpoints],  # type: ignore[misc]
            bands,
            rlatt,
            self.efermi,
            labels_dict={
                k: Kpoint(v, lattice=rlatt).frac_coords  # type: ignore[misc]
                for k, v in (self.labels_dict or {}).items()
            },
            coords_are_cartesian=False,
            structure=self.structure,
            projections=projections,
        )


class BaseElectronicDos(BandTheoryBase):
    """Basic structure for spin-resolved density of states (DOS).

    Note that this class is intended for storing:
        1. Total DOS.
        2. A single-orbital-resolved component of a site- and orbital-
            projected DOS.
    """

    spin_up_densities: list[float] | None = Field(None, description="The spin-up DOS.")

    spin_down_densities: list[float] | None = Field(
        None, description="The spin-down DOS."
    )

    energies: list[float] | None = Field(
        None, description="The energies at which the DOS was calculated."
    )

    efermi: float | None = Field(None, description="The Fermi energy.")

    orbital: str | None = Field(
        None, description="The orbital character of this DOS, if applicable."
    )

    def to_pmg(self) -> Dos:
        """Convert to a pymatgen DOS object."""
        densities = {}
        for spin in Spin:
            if sr_density := getattr(self, f"spin_{spin.name}_densities", None):
                densities[spin] = sr_density
        return Dos(self.efermi, self.energies, densities)  # type: ignore[arg-type]


class ElectronicDos(BaseElectronicDos):
    """Electronic density of states (DOS) with possible projections."""

    projected_densities: list[list[BaseElectronicDos] | None] | None = Field(
        None, description="The orbital- and site-projected DOS."
    )

    @property
    def _available_spins(self) -> list[Spin]:
        """Retrive spin indices of non-null spin data."""
        return [
            spin
            for spin in Spin
            if getattr(self, f"spin_{spin.name}_densities", None) is not None
        ]

    @classmethod
    def from_pmg(cls, dos: Dos | CompleteDos, **kwargs) -> Self:
        """Create an electronic DOS from a pymatgen object."""

        densities: dict[str, list[float]] = {
            f"spin_{spin.name}_densities": list(sr_dos)
            for spin, sr_dos in dos.densities.items()
        }

        if isinstance(dos, CompleteDos):

            pdos: list[list[BaseElectronicDos] | None] | None = None
            if (vrun_pdos := dos.pdos) and dos.structure:
                pdos_dct: dict[int, list[BaseElectronicDos] | None] = {}
                for site, orb_spin_dos in vrun_pdos.items():
                    site_idx: int = [
                        idx
                        for idx, ref_site in enumerate(dos.structure)
                        if ref_site == site
                    ][0]
                    pdos_dct[site_idx] = [
                        BaseElectronicDos(
                            **{  # type: ignore[arg-type]
                                f"spin_{spin.name}_densities": sr_dos
                                for spin, sr_dos in spin_dos.items()
                            },
                            orbital=orbital.name,
                        )
                        for orbital, spin_dos in orb_spin_dos.items()
                    ]
                pdos = [pdos_dct[idx] for idx in sorted(pdos_dct)]

        return cls(
            **densities,  # type: ignore[arg-type]
            efermi=dos.efermi,
            energies=dos.energies.tolist(),
            structure=getattr(dos, "structure", None),
            projected_densities=pdos,
            **kwargs,
        )

    def to_pmg(self) -> Dos | CompleteDos:
        """Serialize to pymatgen."""
        if self.efermi is None:
            raise ValueError(
                "Fermi level unspecified, cannot create a pymatgen (Complete)Dos object."
            )

        densities: dict[Spin, np.ndarray] = {}
        for spin in self._available_spins:
            if (
                _dens := getattr(self, f"spin_{spin.name}_densities", None)
            ) is not None:
                densities[spin] = np.array(_dens)

        dos = Dos(self.efermi, np.array(self.energies), densities)
        if self.structure and self.projected_densities:

            pdos: dict[PeriodicSite, dict[Orbital, dict[Spin, np.ndarray]]] = {}
            for isite, site in enumerate(self.structure):
                pdos[site] = {}
                if not self.projected_densities[isite]:
                    continue
                for site_dos in self.projected_densities[
                    isite
                ]:  # type:ignore[union-attr]
                    if not site_dos.orbital:
                        continue
                    orbital = Orbital[site_dos.orbital]
                    pdos[site][orbital] = {}
                    for spin in self._available_spins:
                        if (
                            _pdos := getattr(
                                site_dos, f"spin_{spin.name}_densities", None
                            )
                        ) is not None:
                            pdos[site][orbital][spin] = np.array(_pdos)

            return CompleteDos(self.structure, dos, pdos)

        return dos
