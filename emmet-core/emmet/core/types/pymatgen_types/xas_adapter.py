from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.analysis.xas.spectrum import XAS
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)

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
        "structure": TypedStructureDict,
        "absorbing_element": TypedElementDict,
        "edge": str,
        "spectrum_type": str,
        "absorbing_index": int,
    },
)


XASTypeVar = TypeVar("XASTypeVar", XAS, TypedXASSpectrumDict)


def pop_xas_empty_structure_fields(xas: XASTypeVar, eps: float = 1e-12):
    """Remove empty keys in the XAS dict and ensure that the spectral data are positive."""
    if isinstance(xas, dict):
        clean_structure = pop_empty_structure_keys(xas["structure"])
        xas["structure"] = clean_structure
        xas["y"] = [y if y > 0.0 else abs(eps) for y in xas["y"]]
        return XAS.from_dict(xas)

    return xas


XASType = Annotated[
    XASTypeVar,
    BeforeValidator(pop_xas_empty_structure_fields),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedXASSpectrumDict),
]
