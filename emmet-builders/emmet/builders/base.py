from pydantic import Field
from pymatgen.core import Structure

from emmet.core.base import EmmetBaseModel
from emmet.core.types.typing import IdentifierType


class BaseBuilderInput(EmmetBaseModel):
    """
    Document model with the minimum inputs required
    to run builders that only require a Pymatgen structure
    object for property analysis.

    A material_id and builder_meta information may be optionally
    included.
    """

    deprecated: bool = Field(False)
    material_id: IdentifierType | None = Field(None)
    structure: Structure
