# isort: off
"""Stub a few pymatgen classes with non-MSONable behavior."""

from typing import TYPE_CHECKING
import pymatgen.core.composition
from pydantic import RootModel
from pymatgen.core import Element, Species

if TYPE_CHECKING:
    from typing import Any

"""
The stub names are kept in sync with the actual classes so they
show up correctly in the JSON Schema. They are imported here
in as Stubbed classes to prevent name clashing
"""


class StubComposition(RootModel):
    """A dictionary mapping element to total quantity"""

    root: dict[Element | Species, float]


@classmethod  # type: ignore
def get_validators(cls):
    yield validate_composition


def validate_composition(cls, v: Any) -> pymatgen.core.composition.Composition:
    if isinstance(v, pymatgen.core.structure.Composition):
        return v
    return pymatgen.core.composition.Composition(**v)


setattr(pymatgen.core.composition.Composition, "__pydantic_model__", StubComposition)
setattr(pymatgen.core.composition.Composition, "__get_validators__", get_validators)
