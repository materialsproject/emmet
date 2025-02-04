import pymatgen.phonon.ir_spectra
from pydantic import RootModel
from pymatgen.core.structure import Structure
from typing_extensions import TypedDict

TypedIRDTensorDict = TypedDict(
    "TypedIRDTensorDict",
    {
        "@module": str,
        "@class": str,
        "oscillator_strength": list[float],
        "ph_freqs_gamma": list[float],
        "structure": Structure,
        "epsilon_infinity": list[float],
    },
)


class IRDielectricTensorAdapter(RootModel):
    root: TypedIRDTensorDict


pymatgen.phonon.ir_spectra.IRDielectricTensor.__pydantic_model__ = (
    IRDielectricTensorAdapter
)
