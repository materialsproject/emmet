from typing_extensions import TypedDict

from emmet.core.serialization_adapters.structure_adapter import TypedStructureDict

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
