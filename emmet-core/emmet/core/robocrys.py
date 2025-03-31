from typing import Optional, Union

from pydantic import BaseModel, Field
from pymatgen.core.structure import Structure

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID
from emmet.core.utils import generate_robocrys_condensed_struct_and_description


class MineralData(BaseModel):
    """
    Model for mineral data in the condensed structure robocrystallographer field
    """

    type: Union[str, None] = Field(
        description="Mineral type.",
    )

    name: Optional[str] = Field(None, description="The mineral name if found.")


class CondensedStructureData(BaseModel):
    """
    Model for data in the condensed structure robocrystallographer field
    More details: https://hackingmaterials.lbl.gov/robocrystallographer/format.html
    """

    mineral: MineralData = Field(
        description="Matched mineral data for the material.",
    )

    dimensionality: int = Field(
        description="Dimensionality of the material.",
    )

    formula: Optional[str] = Field(
        None,
        description="Formula for the material.",
    )

    spg_symbol: Optional[str] = Field(
        None,
        description="Space group symbol of the material.",
    )

    crystal_system: Optional[str] = Field(
        None,
        description="Crystal system of the material.",
    )


class RobocrystallogapherDoc(PropertyDoc):
    """
    This document contains the descriptive data from robocrystallographer
    for a material:
        Structural features, mineral prototypes, dimensionality, ...

    """

    property_name: str = "robocrys"

    description: str = Field(
        description="Description text from robocrytallographer.",
    )

    condensed_structure: CondensedStructureData = Field(
        description="Condensed structure data from robocrytallographer.",
    )

    robocrys_version: str = Field(
        ...,
        description="The version of Robocrystallographer used to generate this document.",
    )

    @classmethod
    def from_structure(
        cls,
        structure: Structure,
        robocrys_version: str,
        material_id: MPID | None = None,
        mineral_matcher=None,
        **kwargs
    ):
        (
            condensed_structure,
            description,
        ) = generate_robocrys_condensed_struct_and_description(
            structure=structure, mineral_matcher=mineral_matcher
        )

        return super().from_structure(
            meta_structure=structure,
            material_id=material_id,
            condensed_structure=condensed_structure,
            description=description,
            robocrys_version=robocrys_version,
            **kwargs
        )
