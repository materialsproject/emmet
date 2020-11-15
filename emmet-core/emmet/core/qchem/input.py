""" Core definition of a Q-Chem calculation input """

from typing import Dict

from pydantic import BaseModel, Field

from emmet.stubs import Molecule


class InputSummary(BaseModel):
    """
    Summary of inputs for a Q-Chem calculation
    """

    molecule: Molecule = Field(
        None, description="The input Molecule for this calculation"
    )

    functional: str = Field(
        None, description="Density functional used for this calculation"
    )

    basis: str = Field(None, description="Basis set used for this calculation")

    solvent_parameters: Dict = Field(
        None, description="Solvent model used for this calculations"
    )

    parameters: Dict = Field(
        None, description="Q-Chem input parameters for this calculation"
    )
