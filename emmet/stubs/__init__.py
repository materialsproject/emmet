from emmet.stubs.utils import patch_msonable, use_model
from emmet.stubs.pymatgen import Structure as StubStructure
from emmet.stubs.pymatgen import Composition as StubComposition
from pymatgen import Structure, Composition

use_model(Structure, StubStructure)
use_model(Composition, StubComposition)
