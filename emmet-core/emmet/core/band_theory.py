"""Define basic schema for band theoretic properties."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, Field, model_validator, model_serializer

from pymatgen.core import Lattice, Structure
from pymatgen.electronic_structure.bandstructure import (
    BandStructure as PmgBandStructure,
    Kpoint,
)
from pymatgen.electronic_structure.core import Spin

from emmet.core.math import Vector3D, Matrix3D

if TYPE_CHECKING:

    from typing_extensions import Self

BAND_GAP_TOL = 1e-4


class BandStructure(BaseModel):
    """Define the schema of band structures.

    This class is generic enough to accommodate both
    electronic and phonon band structures.
    """

    qpoints: list[Vector3D] = Field(
        description="The wave vectors (q-points) at which the band structure was sampled, in direct coordinates.",
    )

    reciprocal_lattice: Matrix3D = Field(description="The reciprocal lattice.")

    labels_dict: dict[str, Vector3D] | None = Field(
        None, description="The high-symmetry labels of specific q-points."
    )

    structure: Structure | None = Field(
        None, description="The structure associated with the calculation."
    )

    @model_validator(mode="before")
    def deserialize_pmg(cls, config: Any) -> Any:
        """Deserialize dict and json.dumps-like pymatgen objects."""

        if config.get("structure"):
            if isinstance(config["structure"], str):
                config["structure"] = Structure.from_str(
                    config["structure"], fmt="json"
                )
            elif isinstance(config["structure"], dict):
                config["structure"] = Structure.from_dict(config["structure"])
        return config

    @model_serializer
    def serialize_pmg(self) -> dict[str, Any]:
        """Serialize pymatgen objects to dicts."""
        config = {k: getattr(self, k, None) for k in type(self).model_fields}
        if config.get("structure"):
            config["structure"] = config["structure"].as_dict()  # type: ignore[union-attr]
        return config


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

    is_metal: bool | None = Field(
        None, description="Whether the band gap is almost zero."
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

    @model_validator(mode="before")
    def deserialize_pmg(cls, config: Any) -> Any:
        """Ensure fields are correctly populated."""

        if bg := config.get("band_gap"):
            if not (config.get("is_metal")):
                config["is_metal"] = bg < BAND_GAP_TOL

        # remap legacy fields
        for k, v in {
            "lattice_rec": "reciprocal_lattice",
            "bands": "frequencies",
        }.items():
            if config.get(k) is not None:
                config[v] = config.pop(k)

        if isinstance(config["reciprocal_lattice"], dict):
            config["reciprocal_lattice"] = config["reciprocal_lattice"].get("matrix")

        return super(ElectronicBS, cls).deserialize_pmg(config)  # type: ignore[operator]

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
            if v := getattr(self, f"spin_{spin.name}_bands"):
                bands[spin] = np.array(v)
            if v := getattr(self, f"spin_{spin.name}_projections"):
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
