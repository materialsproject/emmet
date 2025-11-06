from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field, model_validator
from pymatgen.analysis.diffraction.xrd import WAVELENGTHS, XRDCalculator
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Element

from emmet.core.spectrum import SpectrumDoc
from emmet.core.types.enums import ValueEnum

if TYPE_CHECKING:
    from emmet.core.types.typing import IdentifierType

from emmet.core.types.pymatgen_types.diffraction_pattern_adapter import (
    DiffractionPatternType,
)
from emmet.core.types.pymatgen_types.element_adapter import ElementType


class Edge(ValueEnum):
    K_Alpha = "Ka"
    K_Alpha1 = "Ka1"
    K_Alpha2 = "Ka2"
    K_Beta = "Kb"
    K_Beta1 = "Kb1"
    K_Beta2 = "Kb2"


class XRDDoc(SpectrumDoc):
    """
    Document describing a XRD Diffraction Pattern
    """

    spectrum_name: str = "XRD"

    spectrum: DiffractionPatternType  # type: ignore[valid-type]
    min_two_theta: float
    max_two_theta: float
    wavelength: float = Field(..., description="Wavelength for the diffraction source.")
    target: ElementType | None = Field(
        None, description="Target element for the diffraction source."
    )
    edge: Edge | None = Field(
        None, description="Atomic edge for the diffraction source."
    )

    @model_validator(mode="before")
    @classmethod
    def get_target_and_edge(cls, values: dict):
        # Only do this if neither target not edge is defined
        if "target" not in values and "edge" not in values:
            try:
                pymatgen_wavelength = next(
                    k
                    for k, v in WAVELENGTHS.items()
                    if np.allclose(values["wavelength"], v)
                )
                values["target"] = pymatgen_wavelength[:2]
                values["edge"] = pymatgen_wavelength[2:]

            except Exception:
                return values
        return values

    @classmethod
    def from_structure(  # type: ignore[override]
        cls,
        spectrum_id: str,
        structure: Structure,
        wavelength: float,
        material_id: IdentifierType | None = None,
        min_two_theta=0,
        max_two_theta=180,
        symprec=0.1,
        **kwargs,
    ) -> "XRDDoc":
        calc = XRDCalculator(wavelength=wavelength, symprec=symprec)
        pattern = calc.get_pattern(
            structure, two_theta_range=(min_two_theta, max_two_theta)
        )

        return super().from_structure(
            material_id=material_id,
            spectrum_id=spectrum_id,
            meta_structure=structure,
            spectrum=pattern,
            wavelength=wavelength,
            min_two_theta=min_two_theta,
            max_two_theta=max_two_theta,
            **kwargs,
        )

    @classmethod
    def from_target(
        cls,
        structure: Structure,
        target: Element,
        edge: Edge,
        material_id: IdentifierType | None = None,
        min_two_theta=0,
        max_two_theta=180,
        symprec=0.1,
        **kwargs,
    ) -> "XRDDoc":
        if f"{target}{edge}" not in WAVELENGTHS:
            raise ValueError(f"{target}{edge} not in pymatgen wavelengths dictionary")

        wavelength = WAVELENGTHS[f"{target}{edge}"]
        spectrum_id = f"{material_id}-{target}{edge}"

        return cls.from_structure(
            material_id=material_id,
            spectrum_id=spectrum_id,
            structure=structure,
            wavelength=wavelength,
            target=target,
            edge=edge,
            min_two_theta=min_two_theta,
            max_two_theta=max_two_theta,
            symprec=symprec,
            **kwargs,
        )
