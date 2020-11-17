""" Core definition of a Q-Chem calculation input """

from typing import Dict

from pydantic import BaseModel, Field

from emmet.stubs import Molecule
from emmet.core.qchem.calc_types import LevelOfTheory


class InputSummary(BaseModel):
    """
    Summary of inputs for a Q-Chem calculation
    """

    molecule: Molecule = Field(
        None, description="The input Molecule for this calculation"
    )

    level_of_theory: LevelOfTheory = Field(
        None,
        description="The level of theory for this calculation"
    )

    parameters: Dict = Field(
        None, description="Q-Chem input parameters for this calculation"
    )
