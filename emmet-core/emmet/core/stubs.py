# isort: off
"""
This module stubs some pymatgen classes that implement custom behavior
outside the standard MSONable model
"""
from typing import Dict

import pymatgen.core.structure
from pydantic import BaseModel
from pymatgen.core.periodic_table import Element

"""
The stub names are kept in sync with the actual classes so they
show up correctly in the JSON Schema. They are imported here
in as Stubbed classes to prevent name clashing
"""


class StubComposition(BaseModel):
    """A dictionary mapping element to total quantity"""

    __root__: Dict[Element, float]


@classmethod  # type: ignore
def get_validators(cls):
    yield validate_composition


def validate_composition(cls, v):
    if isinstance(v, pymatgen.core.structure.Composition):
        return v
    return pymatgen.core.structure.Composition(**v)


pymatgen.core.structure.Composition.__pydantic_model__ = StubComposition
pymatgen.core.structure.Composition.__get_validators__ = get_validators
