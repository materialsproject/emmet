""" Core definitions of solvent parameters """

from typing import Dict
from pathlib import Path

from pydantic import Field, BaseModel

from monty.serialization import loadfn

from emmet.core.utils import ValueEnum


# Taken from rubicon
_PCM_IDENTITIES = loadfn(str(Path(__file__).parent.joinpath("pcm_data.json").resolve()))

# Taken largely from rubicon, with some from our database
_SMX_IDENTITIES = loadfn(str(Path(__file__).parent.joinpath("smx_data.json").resolve()))


class SolventModel(ValueEnum):
    """
    Solvent model
    """

    VACUUM = "vacuum"
    PCM = "PCM"
    SMX = "SMX"


class SolventData(BaseModel):
    """
    Data model for solvent parameters
    """

    name: str = Field(None, description="Name of solvent")

    model: SolventModel = Field(None, description="Solvent model used")

    dielectric: float = Field(None, description="Dielectric constant of the solvent")

    refractive_index: float = Field(None, description="Refractive index of the solvent")

    abraham_acidity: float = Field(
        None,
        description="Abraham hydrogen bond acidity of the solvent"
    )

    abraham_basicity: float = Field(
        None,
        description="Abraham hydrogen bond basicity of the solvent"
    )

    surface_tension: float = Field(
        None,
        description="Macroscopic surface tension at the air/solvent interface"
    )

    aromaticity: float = Field(
        None,
        description="Non-hydrogen aromaticity of the solvent"
    )

    halogenicity: float = Field(
        None,
        description="Fraction of non-hydrogen solvent atoms that are F, Cl, or Br"
    )

    pcm_params: Dict = Field(
        None,
        description="Additional parameters for calculations using a PCM solvent model"
    )

    smx_params: Dict = Field(
        None,
        description="Additional parameters for calculations using an SMX solvent model"
    )