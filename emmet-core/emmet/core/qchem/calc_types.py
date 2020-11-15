""" Module to define various calculation types for Q-Chem """
import datetime
from itertools import groupby, product
from pathlib import Path
from typing import Dict, Iterator, List

import bson
import numpy as np
from monty.json import MSONable
from monty.serialization import loadfn
from pydantic import BaseModel, Field
from pymatgen.core.structure import Structure
from typing_extensions import Literal

from emmet.core import SETTINGS
from emmet.core.utils import ValueEnum
from emmet.core.qchem.solvent import SolventModel, SolventData


_TASK_TYPES = [
    "Single point",
    "Geometry optimization",
    "Frequency analysis",
    "Transition state optimization",
    "Frequency flattening optimization",
    "Frequency flattening transition state optimization",
    "Critical point analysis"
]
TaskType = ValueEnum("TaskType", {"_".join(tt.split()): tt for tt in _TASK_TYPES})  # type: ignore
TaskType.__doc__ = "Q-Chem calculation task types"


class LevelOfTheory(BaseModel):
    """
    Data model for calculation level of theory
    """

    functional: str = Field(..., description="Exchange-correlation density functional")

    basis: str = Field(..., description="Basis set name")

    solvent_data: SolventData = Field(None, description="Implicit solvent model")

    correction_functional: str = Field(
        None,
        description="Exchange-correlation density functional used for energy corrections"
    )

    correction_basis: str = Field(
        None,
        description="Basis set name used for energy corrections"
    )

    correction_solvent_data: SolventData = Field(
        None,
        description="Implicit solvent model used for energy corrections"
    )

    @property
    def solvent_model(self):
        if self.solvent_data is None:
            return SolventData("vacuum")
        else:
            return self.solvent_data.solvent_model