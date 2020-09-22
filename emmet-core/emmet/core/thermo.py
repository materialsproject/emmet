""" Core definition of a Thermo Document """
from datetime import datetime
from typing import ClassVar, Dict, List
from enum import Enum

from pydantic import BaseModel, Field
from pymatgen.core.periodic_table import Element

from emmet.core.material import PropertyDoc
from emmet.core.structure import StructureMetadata
from emmet.stubs import ComputedEntry, Composition


class DecompositionProduct(BaseModel):
    """
    Entry metadata for a decomposition process
    """

    material_id: str = Field(
        None, description="The material this decomposition points to"
    )
    formula: str = Field(
        None,
        description="The formula of the decomposed material this material decomposes to",
    )
    amount: float = Field(
        None,
        description="The amount of the decomposed material by formula units this this material decomposes to",
    )


class Thermo(PropertyDoc):
    """
    A thermo entry document
    """

    property_name: ClassVar[str] = Field(
        "thermo", description="The subfield name for this property"
    )

    uncorrected_energy_per_atom: float = Field(
        None, description="The total DFT energy of this material per atom in eV/atom"
    )

    energy_per_atom: float = Field(
        None,
        description="The total corrected DFT energy of this material per atom in eV/atom",
    )

    energy_uncertainy_per_atom: float = Field(
        None, description=""
    )  # From correction_uncertainty / N

    formation_energy_per_atom: float = Field(
        None, description="The formation energy per atom in eV/atom"
    )
    e_above_hull: float = Field(
        None, description="The energy above the hull in eV/Atom"
    )
    is_stable: bool = Field(
        None,
        description="Flag for whether this material is on the hull and therefore stable",
    )
    equillibrium_reaction_energy_per_atmo: float = Field(
        None,
        description="The reaction energy of a stable entry from the neighboring equilibrium stable materials in eV."
        " Also known as the inverse distance to hull.",
    )

    decomposes_to: List[DecompositionProduct] = Field(
        None,
        description="List of decomposition data for this material. Only valid for metastable or unstable material.",
    )

    energy_type: str = Field(
        None,
        description="The type of calculation this energy evaluation comes from. TODO: Convert to enum?",
    )

    entry_types: List[str] = Field(
        description="List of available energy types computed for this material"
    )

    entries: Dict[str, ComputedEntry] = Field(
        None,
        description="List of all entries that are valid for this material."
        " The keys for this dictionary are names of various calculation types",
    )
