"""Core definition of a Materials Document"""

from __future__ import annotations

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

from emmet.core.material import BasePropertyMetadata
from emmet.core.types.pymatgen_types.structure_adapter import StructureType


class PropertyDoc(BasePropertyMetadata):
    """
    Base model definition for any singular materials property.

    This may contain any amount of structure metadata for the
    purpose of search. This is intended to be inherited and
    extended, not used directly
    """

    property_name: str

    structure: SkipJsonSchema[StructureType | None] = Field(
        None, description="The structure associated with this property.", exclude=True
    )
