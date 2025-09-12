from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.phonon.ir_spectra import IRDielectricTensor
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.structure_adapter import TypedStructureDict

TypedIRDTensorDict = TypedDict(
    "TypedIRDTensorDict",
    {
        "@module": str,
        "@class": str,
        "oscillator_strength": list[float],
        "ph_freqs_gamma": list[float],
        "structure": TypedStructureDict,
        "epsilon_infinity": list[float],
    },
)

IRDielectricTensorTypeVar = TypeVar(
    "IRDielectricTensorTypeVar", IRDielectricTensor, TypedIRDTensorDict
)

IRDielectricTensorType = Annotated[
    IRDielectricTensorTypeVar,
    BeforeValidator(
        lambda x: IRDielectricTensor.from_dict(x) if isinstance(x, dict) else x
    ),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedIRDTensorDict),
]
