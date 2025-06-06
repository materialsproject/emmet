from typing import TypeVar

from pymatgen.core import Composition
from pymatgen.core.periodic_table import Element

CompositionTypeVar = TypeVar("CompositionTypeVar", Composition, dict[Element, float])
