""" Core definition of a Materials Document """
from typing import List, Dict, ClassVar, Union
from functools import partial
from datetime import datetime

from pydantic import BaseModel, Field, create_model

from pymatgen.analysis.magnetism import Ordering, CollinearMagneticStructureAnalyzer

from emmet.stubs import Structure
from emmet.core.structure import StructureMetadata
from emmet.core.material import PropertyOrigin


class PropertyDoc(BaseModel):
    """
    Prototype document structure for any materials property document
    """

    property_name: ClassVar[str] = Field(
        None, description="The subfield name for this property"
    )


class MaterialsProperty(StructureMetadata):
    """
    Base model definition for any singular materials property. This may contain any amount
    of structure metadata for the purpose of search
    This is intended to be inherited and extended not used directly
    """

    material_id: str = Field(
        ...,
        description="The ID of the material, used as a universal reference across proeprty documents."
        "This comes in the form: mp-******",
    )

    last_updated: datetime = Field(
        None,
        description="Timestamp for the most recent calculation update for this property",
    )

    origins: List[PropertyOrigin] = Field(
        [], description="Dictionary for tracking the provenance of properties"
    )

    warnings: List[str] = Field(
        None, description="Any warnings related to this property"
    )

    sandboxes: List[str] = Field(
        None,
        description="List of sandboxes this material belongs to."
        " Sandboxes provide a way of controlling access to materials."
        " No sandbox means this materials is openly visible",
    )

    @staticmethod
    def to_subdoc(data: Union["MaterialsProperty", Dict]):
        """
        Converts  to a property subdocument
        """
        to_remove_fields = set(MaterialsProperty.__fields__) - set("last_updated")

        subdoc = data.dict() if isinstance(data, MaterialsProperty) else data
        subdoc = {k: v for k, v in subdoc if k not in to_remove_fields}

        return subdoc

    @classmethod
    def __class_getitem__(cls, parameters):
        """
        Enables generating dynamic sub types of MaterialDocument
        Can provide either 1 BaseModel class or any number of BaseModel classes if proceeded by a string
        """
        model_name = None
        subdocs = {}
        if parameters == ():
            raise TypeError("Cannot make a Material Property of no sub documents")

        if not isinstance(parameters, tuple):
            if issubclass(parameters, PropertyDoc):
                model_name = f"{parameters.property_name.title()}Doc"
                subdocs = {parameters.property_name: (parameters, None)}
            else:
                raise ValueError("Must provide PropertyDocs")

        elif len(parameters > 1):
            if not isinstance(parameters[0], str):
                raise ValueError(
                    "Must provide new document name as the first parameter when making a multi-property document"
                )
            else:
                model_name = parameters[0]
                parameters = parameters[1:]
                if not all(issubclass(s, PropertyDoc) for s in parameters):
                    raise ValueError("Must provide PropertyDocs")
                subdocs = {s.property_name: (s, None) for s in parameters}
        else:
            raise ValueError(
                "Must provide at minimum one string for the name and one PropertyDoc subtype"
            )

        new_model = create_model(model_name=model_name, __base__=cls, **subdocs)

        return new_model
