from emmet.stubs.utils import patch_msonable, use_model
from emmet.stubs.pymatgen import Structure as StubStructure
from pymatgen import Structure

use_model(Structure, StubStructure)
