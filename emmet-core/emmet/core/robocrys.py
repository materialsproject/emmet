from __future__ import annotations
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pymatgen.core.structure import Structure

from emmet.core.material_property import PropertyDoc
from emmet.core.utils import generate_robocrys_condensed_struct_and_description

if TYPE_CHECKING:
    from emmet.core.types.typing import IdentifierType


class MineralData(BaseModel):
    """
    Model for mineral data in the condensed structure robocrystallographer field
    """

    type: str | None = Field(
        None,
        description="Mineral type.",
    )

    name: str | None = Field(None, description="The mineral name if found.")


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

    formula: str | None = Field(
        None,
        description="Formula for the material.",
    )

    spg_symbol: str | None = Field(
        None,
        description="Space group symbol of the material.",
    )

    crystal_system: str | None = Field(
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
        material_id: IdentifierType | None = None,
        mineral_matcher=None,
        **kwargs,
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
            **kwargs,
        )
