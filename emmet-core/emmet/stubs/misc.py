from typing import Dict

from pydantic import BaseModel
from pymatgen.core.periodic_table import Element


class Composition(BaseModel):
    """A dictionary mapping element to total quantity"""

    __root__: Dict[Element, float]
