import pymatgen.core.composition
from pydantic import RootModel
from pymatgen.core.periodic_table import Element


class CompositionAdapter(RootModel):
    """A dictionary mapping element to total quantity"""

    root: dict[Element, float]


setattr(pymatgen.core.composition.Composition, "__type_adapter__", CompositionAdapter)
