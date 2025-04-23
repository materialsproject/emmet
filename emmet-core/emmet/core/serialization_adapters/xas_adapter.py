from typing import Annotated, TypeVar

import pymatgen.analysis.xas.spectrum
from pydantic import RootModel
from pydantic.functional_validators import BeforeValidator
from pymatgen.core import Structure
from typing_extensions import TypedDict

from emmet.core.serialization_adapters.structure_adapter import pop_empty_structure_keys

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


setattr(pymatgen.analysis.xas.spectrum.XAS, "__type_adapter__", XASSpectrumAdapter)

XASTypeVar = TypeVar("XASTypeVar", pymatgen.analysis.xas.spectrum.XAS, dict)


def pop_xas_empty_structure_fields(xas: XASTypeVar):
    if isinstance(xas, dict):
        clean_structure = pop_empty_structure_keys(xas["structure"])
        xas["structure"] = clean_structure

    return xas


AnnotatedXAS = Annotated[XASTypeVar, BeforeValidator(pop_xas_empty_structure_fields)]
