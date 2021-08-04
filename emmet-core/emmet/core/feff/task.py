""" Core definition of a VASP Task Document """
from typing import Any, Dict, List

from pydantic import Field
from pymatgen.analysis.xas.spectrum import XAS
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Element

from emmet.core.structure import StructureMetadata
from emmet.core.task import TaskDocument as BaseTaskDocument
from emmet.core.utils import ValueEnum


class CalcType(ValueEnum):
    """
    The type of FEFF Calculation
    XANES - Just the near-edge region
    EXAFS - Just the extended region
    XAFS - Fully stitchted XANES + EXAFS
    """

    XANES = "XANES"
    EXAFS = "EXAFS"
    XAFS = "XAFS"


class TaskDocument(BaseTaskDocument, StructureMetadata):
    """Task Document for a FEFF XAS Calculation. Doesn't support EELS for now"""

    calc_code = "FEFF"

    structure: Structure
    input_parameters: Dict[str, Any] = Field(
        {}, description="Input parameters for the FEFF calculation"
    )
    spectrum: List[List[float]] = Field(
        [[]], description="Raw spectrum data from FEFF xmu.dat or eels.dat"
    )

    absorbing_atom: int = Field(
        ..., description="Index in the cluster or structure for the absorbing atom"
    )
    spectrum_type: CalcType = Field(..., title="XAS Spectrum Type")
    edge: str = Field(
        ..., title="Absorption Edge", description="The interaction edge for XAS"
    )

    # TEMP Stub properties for compatability with atomate drone

    @property
    def absorbing_element(self) -> Element:
        if isinstance(self.structure[self.absorbing_atom].specie, Element):
            return self.structure[self.absorbing_atom].specie
        return self.structure[self.absorbing_atom].specie.element

    @property
    def xas_spectrum(self) -> XAS:

        if not hasattr(self, "_xas_spectrum"):

            if not all([len(p) == 6 for p in self.spectrum]):
                raise ValueError(
                    "Spectrum data doesn't appear to be from xmu.dat which holds XAS data"
                )

            energy = [point[0] for point in self.spectrum]  # (eV)
            intensity = [point[3] for point in self.spectrum]  # (mu)
            structure = self.structure
            absorbing_index = self.absorbing_atom
            absorbing_element = self.absorbing_element
            edge = self.edge
            spectrum_type = str(self.spectrum_type)

            self._xas_spectrum = XAS(
                x=energy,
                y=intensity,
                structure=structure,
                absorbing_element=absorbing_element,
                absorbing_index=absorbing_index,
                edge=edge,
                spectrum_type=spectrum_type,
            )

        return self._xas_spectrum
