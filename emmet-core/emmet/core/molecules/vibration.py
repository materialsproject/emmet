import warnings
from itertools import groupby
from typing import List

import numpy as np
from pydantic import Field

from pymatgen.core.periodic_table import Element

from emmet.core.mpid import MPID
from emmet.core.spectrum import SpectrumDoc
from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.molecule_property import PropertyDoc


class VibSpectrumDoc(SpectrumDoc):
    pass


class VibrationalModesDoc(PropertyDoc):
    pass