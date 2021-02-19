# isort: off
"""
This module stubs some pymatgen classes that implement custom behavior
outside the standard MSONable model
"""

import pymatgen.core.structure
from pymatgen.core.periodic_table import Element
from pydantic import BaseModel

"""
The stub names are kept in sync with the actual classes so they
show up correctly in the JSON Schema. They are imported here
in as Stubbed classes to prevent name clashing
"""


class StubComposition(BaseModel):
    """A dictionary mapping element to total quantity"""

    __root__: Dict[Element, float]


pymatgen.core.structure.Composition.__pydantic_model__ = StubComposition
