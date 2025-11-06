from typing import TypeVar

from pymatgen.entries.compatibility import (
    Compatibility,
    MaterialsProject2020Compatibility,
    MaterialsProjectAqueousCompatibility,
)
from typing_extensions import TypedDict

TypedCompatibilityDict = TypedDict(
    "TypedCompatibilityDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
    },
)


class TypedMaterialsProject2020CompatibilityAdapterDict(TypedCompatibilityDict):
    """
    Does not define an as_dict() method, parent(Compatibility) is abstract
    so Monty just serializes to module, class, and version.
    """

    pass


class TypedMaterialsProjectAqueousCompatibilityAdapterDict(TypedCompatibilityDict):
    """
    Does not define an as_dict() method, parent(Compatibility) is abstract
    so Monty just serializes to module, class, and version.
    """

    pass


CompatibilityTypeVar = TypeVar(
    "CompatibilityTypeVar", Compatibility, TypedCompatibilityDict
)

MaterialsProjectAqueousCompatibilityAdapterDictTypeVar = TypeVar(
    "MaterialsProjectAqueousCompatibilityAdapterDictTypeVar",
    MaterialsProjectAqueousCompatibility,
    TypedMaterialsProjectAqueousCompatibilityAdapterDict,
)

MaterialsProject2020CompatibilityAdapterDictTypeVar = TypeVar(
    "MaterialsProject2020CompatibilityAdapterDictTypeVar",
    MaterialsProject2020Compatibility,
    TypedMaterialsProject2020CompatibilityAdapterDict,
)
