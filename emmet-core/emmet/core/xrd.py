from typing import ClassVar, Dict

import numpy as np
from pydantic import Field, root_validator
from pymatgen.analysis.diffraction.xrd import (
    WAVELENGTHS,
    DiffractionPattern,
    XRDCalculator,
)
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Element

from emmet.core.mpid import MPID
from emmet.core.spectrum import SpectrumDoc
from emmet.core.utils import ValueEnum


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

    spectrum_name: ClassVar[str] = "XRD"

    spectrum: DiffractionPattern
    min_two_theta: float
    max_two_theta: float
    wavelength: float = Field(..., description="Wavelength for the diffraction source")
    target: Element = Field(
        None, description="Target element for the diffraction source"
    )
    edge: Edge = Field(None, description="Atomic edge for the diffraction source")

    @root_validator(pre=True)
    def get_target_and_edge(cls, values: Dict):
        print("Validations")
        # Only do this if neither target not edge is defined
        if "target" not in values and "edge" not in values:
            print("Are we even getting here?")
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
        material_id: MPID,
        spectrum_id: str,
        structure: Structure,
        wavelength: float,
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
            structure=structure,
            spectrum=pattern,
            wavelength=wavelength,
            min_two_theta=min_two_theta,
            max_two_theta=max_two_theta,
            **kwargs,
        )

    @classmethod
    def from_target(
        cls,
        material_id: MPID,
        structure: Structure,
        target: Element,
        edge: Edge,
        min_two_theta=0,
        max_two_theta=180,
        symprec=0.1,
        **kwargs,
    ) -> "XRDDoc":
        if f"{target}{edge}" not in WAVELENGTHS:
            raise ValueError(f"{target}{edge} not in pymatgen wavelenghts dictionarty")

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
            **kwargs,
        )
