from typing import Union

from pydantic import BaseModel, Field
from pymatgen.core.structure import Structure
from robocrys import StructureCondenser, StructureDescriber
from robocrys import __version__ as __robocrys_version__

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID


class MineralData(BaseModel):
    """
    Model for mineral data in the condensed structure robocrystallographer field
    """

    type: Union[str, None] = Field(
        description="Mineral type.",
    )

    name: str = Field(None, description="The mineral name if found")


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


class RobocrystallogapherDoc(PropertyDoc):
    """
    This document contains the descriptive data from robocrystallographer
    for a material:
        Structural features, mineral prototypes, dimensionality, ...
    """

    description: str = Field(
        description="Decription text from robocrytallographer.",
    )

    condensed_structure: CondensedStructureData = Field(
        description="Condensed structure data from robocrytallographer.",
    )

    robocrys_version: str = Field(
        __robocrys_version__,
        description="The version of Robocrystallographer used to generate this document",
    )

    @classmethod
    def from_structure(cls, structure: Structure, material_id: MPID, **kwargs):  # type: ignore[override]
        condensed_structure = StructureCondenser().condense_structure(structure)
        description = StructureDescriber(
            describe_symmetry_labels=False, fmt="unicode", return_parts=False
        ).describe(condensed_structure=condensed_structure)

        return cls(
            structure=structure,
            material_id=material_id,
            condensed_structure=condensed_structure,
            description=description,
            **kwargs
        )
