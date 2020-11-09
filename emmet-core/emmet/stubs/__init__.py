"""
This module stubs in pydantic models for common MSONable classes, particularly those in Pymatgen
Use pymatgen classes in pydantic models by importing them from there when you need schema

"""

from pymatgen.analysis.xas.spectrum import XAS
from pymatgen.core.structure import Composition, Structure, Lattice
from pymatgen.entries.computed_entries import ComputedEntry

from emmet.stubs.math import Matrix3D, Vector3D
from emmet.stubs.misc import Composition as StubComposition
from emmet.stubs.misc import ComputedEntry as StubComputedEntry
from emmet.stubs.structure import Structure as StubStructure
from emmet.stubs.structure import Lattice as StubLattice

from emmet.stubs.utils import patch_msonable, use_model

"""
The stub names are kept in sync with the actual classes so they
show up correctly in the JSON Schema. They are imported here
in as Stubbed classes to prevent name clashing
"""
use_model(Structure, StubStructure)
use_model(Lattice, StubLattice)
use_model(Composition, StubComposition, add_monty=False)
use_model(ComputedEntry, StubComputedEntry)

# This is after the main block since it depends on that
from emmet.stubs.xas import XASSpectrum  # noqa

use_model(XAS, XASSpectrum)
