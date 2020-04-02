""" Core definition of an Electrode Document """
from typing import List, Dict, ClassVar
from datetime import datetime

from pydantic import BaseModel, Field

from emmet.stubs import ComputedEntry
from emmet.core.structure import StructureMetadata


class ElementEvolution(BaseModel):
    """
    Result of the PhaseDiagram.get element_profile which moves a along a line in
    composition space and return the reaction, chemical potential, and the remaining
    amount of the element
    """
    reaction: str = Field(
        ...,
        description="Evolution reaction determined by a facet of the phase diagram",
    )

    chempot: float = Field(
        ...,
        description="The chemical potential of the target element solved on that facet",
    )

    evolution: float = Field(
        ...,
        description="Remaining amount of element .. TODO get better description",
    )

class VoltagePair(BaseModel):
    """
    Based on AbstractVoltagePair from pymatgen
    """

    voltage: float = Field(
        ...,
        description="Voltage of voltage pair",
    )

    mAh: float = Field(
        ...,
        description="Energy in mAh",
    )

    mass_charge: float = Field(
        ...,
        description= "Mass of charged pair.",
    )

    mass_discharge: float = Field(
        ...,
        description= "Mass of discharged pair.",
    )

    vol_charge: float = Field(
        ...,
        description= "Volume of charged pair.",
    )

    vol_discharge: float = Field(
        ...,
        description= "Volume of discharged pair.",)

    frac_charge: float = Field(
        ...,
        description= "Atomic Fraction of working ion in charged pair.",
    )

    frac_discharge: float = Field(
        ...,
        description= "Atomic Fraction of working ion in discharged pair.",
    )

    working_ion_entry: float = Field(
        ...,
        description= "Working ion as an entry.",
    )


class Electrode(BaseModel):
    """
    Based on AbstractElectrode from pymatgen
    """

    battery_id: str = Field(..., description="The id for this battery document.")

    framework: StructureMetadata = Field(
        ...,
        description="Framework structure (taken from the delithiated form of the most "
                    "lithiated structure)"
    )

    entries: Dict[str, ComputedEntry] = Field(
        ...,
        description="List of all entries used to construct this electrode",
    )

    voltage_pairs: List[VoltagePair] = Field(
        ...,
        description="Returns all the VoltagePairs",
    )

    working_ion: str = Field(
        ...,
        description="The working ion as an Element object",
    )

    working_ion_entry: ComputedEntry = Field(
        ...,
        description = "The working ion as an Entry object",
    )

    max_delta_volume: float = Field(
        ...,
        description = "Maximum volume change along insertion",
    )

    num_steps: float = Field(
        ...,
        description="The number of distinct voltage steps in from fully charge to "
                    "dischargebased on the stable intermediate states")

    max_voltage: float = Field(
        ...,
        description = "Highest voltage along insertion"
    )

    min_voltage: float = Field(
        ...,
        description = "Lowest voltage along insertion"
    )

    max_voltage_step: float = Field(
        ...,
        description="Maximum absolute difference in adjacent voltage steps"
    )

    normalization_mass: float = Field(
        ...,
        description = "Returns: Mass used for normalization. This is the mass of the  " \
                      "discharged electrode of the last voltage pair.
    )

    normalization_volume: float = Field(
        ...,
        description = "Returns: Mass used for normalization. This is the vol of the "
                      "discharged electrode of the last voltage pair"
    )

    last_updated: datetime = Field(
        ..., description="The timestamp when this document was last updated"
    )

