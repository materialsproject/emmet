import pymatgen.core.composition
from pydantic import RootModel
from pymatgen.core.periodic_table import Element


class CompositionAdapter(RootModel):
    """A dictionary mapping element to total quantity"""

    root: dict[Element, float]


@classmethod
def get_validators(cls):
    yield validate_composition


def validate_composition(cls, v):
    if isinstance(v, pymatgen.core.structure.Composition):
        return v
    return pymatgen.core.composition.Composition(**v)


pymatgen.core.composition.Composition.__pydantic_model__ = CompositionAdapter
pymatgen.core.composition.Composition.__get_validators__ = get_validators
