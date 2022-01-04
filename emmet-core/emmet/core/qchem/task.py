""" Core definition of a Q-Chem Task Document """
from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field
from pymatgen.core.structure import Molecule

from emmet.core.math import Matrix3D, Vector3D
from emmet.core.structure import StructureMetadata
from emmet.core.task import TaskDocument as BaseTaskDocument
from emmet.core.utils import ValueEnum
from emmet.core.vasp.calc_types import RunType, calc_type, run_type, task_type