"""
This module stubs in pydantic models for common MSONable classes, particularly those in Pymatgen
Use pymatgen classes in pydantic models by importing them from there when you need schema

"""

from emmet.stubs.utils import patch_msonable, use_model
from emmet.stubs.structure import Structure as StubStructure
from emmet.stubs.misc import Composition as StubComposition
from emmet.stubs.misc import ComputedEntry as StubComputedEntry
from emmet.stubs.math import Vector3D, Matrix3D
from pymatgen import Structure, Composition
from pymatgen.entries.computed_entries import ComputedEntry

"""
The stub names are kept in sync with the actual classes so they
show up correctly in the JSON Schema. They are imported here
in as Stubbed classes to prevent name clashing
"""


use_model(Structure, StubStructure)
use_model(Composition, StubComposition, add_monty=False)
use_model(ComputedEntry, StubComputedEntry)
