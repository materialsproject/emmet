import pymatgen.analysis.xas.spectrum
from pydantic import RootModel
from pymatgen.core import Structure
from typing_extensions import TypedDict

TypedElementDict = TypedDict(
    "TypedElementDict",
    {"@module": str, "@class": str, "element": str},
)

TypedXASSpectrumDict = TypedDict(
    "TypedXASSpectrumDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "x": list[float],
        "y": list[float],
        "structure": Structure,
        "absorbing_element": TypedElementDict,
        "edge": str,
        "spectrum_type": str,
        "absorbing_index": int,
    },
)


class XASSpectrumAdapter(RootModel):
    root: TypedXASSpectrumDict


pymatgen.analysis.xas.spectrum.XAS.__pydantic_model__ = XASSpectrumAdapter
