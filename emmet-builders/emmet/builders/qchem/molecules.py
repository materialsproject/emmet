from datetime import datetime
from itertools import chain
from math import ceil
from typing import Dict, Iterable, Iterator, List, Optional

from maggma.builders import Builder
from maggma.stores import Store
from maggma.utils import grouper

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.utils import group_structures, jsanitize
from emmet.core.vasp.material import MaterialsDoc
from emmet.core.vasp.task import TaskDocument

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"

SETTINGS = EmmetBuildSettings()