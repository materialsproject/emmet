import warnings
from itertools import groupby
from typing import List
from datetime import datetime

import numpy as np
from pydantic import Field

from pymatgen.core.structure import Molecule

from emmet.core.mpid import MPID
from emmet.core.structure import MoleculeMetadata
from emmet.core.material import PropertyOrigin
from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"

