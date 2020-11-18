""" Core definitions of solvent parameters """

from typing import Dict, TypeVar, Type, Optional
from pathlib import Path

from pydantic import Field, BaseModel

from monty.serialization import loadfn

from emmet.core.utils import ValueEnum


# Taken from rubicon
_PCM_IDENTITIES = loadfn(str(Path(__file__).parent.joinpath("pcm_data.json").resolve()))

# Taken largely from rubicon, with some from our database
_SMX_IDENTITIES = loadfn(str(Path(__file__).parent.joinpath("smx_data.json").resolve()))


def parse_custom_string(custom_smd):
    entries = custom_smd.split(",")
    keys = [
        "dielectric",
        "refractive_index",
        "abraham_acidity",
        "abraham_basicity",
        "surface_tension",
        "aromaticity",
        "halogenicity"
    ]

    solvent_dict = {k: None for k in keys}

    for ii, entry in entries:
        solvent_dict[keys[ii]] = float(entry)

    return solvent_dict


class SolventModel(ValueEnum):
    """
    Solvent model
    """

    VACUUM = "vacuum"
    PCM = "PCM"
    SMX = "SMX"


S = TypeVar("S", bound="SolventData")


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

    @property
    def smx_string(self):
        if all([x is not None for x in [self.dielectric,
                                        self.refractive_index,
                                        self.abraham_acidity,
                                        self.abraham_basicity,
                                        self.surface_tension,
                                        self.aromaticity,
                                        self.halogenicity]]):
            return "{},{},{},{},{},{},{}".format(
                self.dielectric,
                self.refractive_index,
                self.abraham_acidity,
                self.abraham_basicity,
                self.surface_tension,
                self.aromaticity,
                self.halogenicity
            )
        else:
            raise NotImplementedError("All SMX input variables (dielectric, refractive index, Abraham acidity/basicity"
                                      ", surface tension, aromaticity, and halogenicity must be provided!")

    @classmethod
    def from_input_dict(cls: Type[S], calc_input: Dict, metadata: Optional[Dict] = None) -> S:
        if "rem" not in calc_input:
            raise ValueError("No rem dict provided! calc_input is invalid!")

        if "solvent_method" not in calc_input["rem"]:
            return cls(name="vacuum", model=SolventModel("vacuum"))
        else:
            solvent_method = calc_input["rem"]["solvent_method"].lower()
            if solvent_method.lower() in ["sm8", "sm12", "smd"]:
                smx_params = calc_input.get('smx')
                if smx_params is None:
                    return cls(
                        name="Water",
                        model=SolventModel("SMX"),
                        smx_params=smx_params
                    )
                else:
                    if "solvent" in smx_params:
                        if smx_params["solvent"] == "custom":
                            if metadata is None:
                                return cls(
                                    name="Unknown",
                                    model=SolventModel("SMX"),
                                    smx_params=smx_params
                                )
                            else:
                                custom_smd = metadata.get("custom_smd")
                                if custom_smd in _SMX_IDENTITIES:
                                    name = _SMX_IDENTITIES[metadata.get("custom_smd")]
                                    solvent_params = parse_custom_string(custom_smd)
                                else:
                                    name = "Unknown"
                                    solvent_params = parse_custom_string(custom_smd)

                                return cls(
                                    name=name,
                                    model=SolventModel("SMX"),
                                    dielectric=solvent_params.get("dielectric"),
                                    refractive_index=solvent_params.get("refractive_index"),
                                    abraham_acidity=solvent_params.get("abraham_acidity"),
                                    abraham_basicity=solvent_params.get("abraham_basicity"),
                                    surface_tension=solvent_params.get("surface_tension"),
                                    aromaticity=solvent_params.get("aromaticity"),
                                    halogenicity=solvent_params.get("halogenicity"),
                                    smx_params=smx_params
                                )

                    else:
                        return cls(
                            name="Unknown",
                            model=SolventModel("SMX"),
                            smx_params=smx_params
                        )

            elif solvent_method.lower() in ["pcm", "cosmo"]:
                pcm_params = calc_input.get("pcm", dict())
                pcm_params.update(calc_input.get("solvent", dict()))

                # No PCM parameters
                if pcm_params == dict():
                    return cls(
                        name="Unknown",
                        model=SolventModel("PCM")
                    )
                else:
                    if "dielectric" not in pcm_params:
                        return cls(
                            name="Water",
                            model=SolventModel("PCM"),
                            dielectric=78.39
                        )
                    else:
                        if str(pcm_params["dielectric"]) in _PCM_IDENTITIES:
                            return cls(
                                name=_PCM_IDENTITIES[pcm_params["dielectric"]],
                                model=SolventModel("PCM"),
                                dielectric=float(pcm_params["dielectric"]),
                                pcm_params=pcm_params
                            )
                        else:
                            return cls(
                                name="Unknown",
                                model=SolventModel("PCM"),
                                dielectric=float(pcm_params["dielectric"]),
                                pcm_params=pcm_params
                            )
