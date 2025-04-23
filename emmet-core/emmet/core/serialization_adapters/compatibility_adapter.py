import pymatgen.entries.compatibility
from pydantic import RootModel
from typing_extensions import TypedDict

TypedCompatibilityDict = TypedDict(
    "TypedCompatibilityDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
    },
)


class CompatibilityAdapter(RootModel):
    root: TypedCompatibilityDict


class MaterialsProject2020CompatibilityAdapter(CompatibilityAdapter):
    """
    Does not define an as_dict() method, parent(Compatibility) is abstract
    so Monty just serializes to module, class, and version.
    """

    pass


class MaterialsProjectAqueousCompatibilityAdapter(CompatibilityAdapter):
    """
    Does not define an as_dict() method, parent(Compatibility) is abstract
    so Monty just serializes to module, class, and version.
    """

    pass


setattr(
    pymatgen.entries.compatibility.Compatibility,
    "__type_adapter__",
    CompatibilityAdapter,
)

setattr(
    pymatgen.entries.compatibility.MaterialsProject2020Compatibility,
    "__type_adapter__",
    MaterialsProject2020CompatibilityAdapter,
)

setattr(
    pymatgen.entries.compatibility.MaterialsProjectAqueousCompatibility,
    "__type_adapter__",
    MaterialsProjectAqueousCompatibilityAdapter,
)
