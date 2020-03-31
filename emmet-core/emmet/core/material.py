""" Core definition of a Materials Document """
from typing import List, Dict, ClassVar, Union
from functools import partial
from datetime import datetime

from pydantic import BaseModel, Field, create_model

from emmet.stubs import Structure
from emmet.core.structure import StructureMetadata


class PropertyOrigin(BaseModel):
    """
    Provenance document for the origin of properties in a material document
    """

    name: str = Field(..., description="The materials document property")
    task_type: str = Field(
        ..., description="The original calculation type this propeprty comes from"
    )
    task_id: str = Field(..., description="The calculation ID this property comes from")
    last_updated: datetime = Field(
        ..., description="The timestamp when this calculation was last updated"
    )


class MaterialsDoc(StructureMetadata):
    """
    Definition for a full Materials Document
    Subsections can be defined by other builders
    """

    structure: Structure = Field(
        None, description="The best structure for this material"
    )

    initial_structures: List[Structure] = Field(
        list(),
        description="Initial structures used in the DFT optimizations corresponding to this material",
    )

    task_ids: List[str] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Materials Document",
    )

    deprecated_tasks: List[str] = Field([], title="Deprecated Tasks")

    deprecated: bool = Field(
        None,
        description="Whether this materials document is deprecated due to a lack of high enough quality calculation.",
    )

    # Only material_id is required for all documents
    material_id: str = Field(
        ...,
        description="The ID of this material, used as a universal reference across proeprty documents."
        "This comes in the form: mp-******",
    )

    last_updated: datetime = Field(
        None,
        description="Timestamp for the most recent calculation for this Material document",
    )
    created_at: datetime = Field(
        None,
        description="Timestamp for the first calculation for this Material document",
    )
    task_types: Dict[str, str] = Field(
        {},
        description="Calculation types for all the calculations that make up this material",
    )

    origins: List[PropertyOrigin] = Field(
        [], description="Dictionary for tracking the provenance of properties"
    )

    @classmethod
    def build_from_structure(
        cls, structure: Structure, material_id: str, **kwargs
    ) -> "MaterialsDoc":
        """
        Builds a materials document using the minimal amount of information
        """
        meta = StructureMetadata.from_structure(structure)
        kwargs.update(**meta.dict())

        if "last_updated" not in kwargs:
            kwargs["last_updated"] = datetime.utcnow()

        if "created_at" not in kwargs:
            kwargs["created_at"] = datetime.utcnow()

        return cls(material_id=material_id, **kwargs)


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
