from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.analysis.graphs import MoleculeGraph, StructureGraph
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.molecule_adapter import (
    TypedMoleculeDict,
    pop_empty_molecule_keys,
)
from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedStructureDict,
    pop_empty_structure_keys,
)

GraphDescriptors = list[str, str]  # type: ignore[type-arg]


class TypedNodeDict(TypedDict):
    id: int


class TypedAdjacencyDict(TypedDict):
    to_jimage: list[int, int, int]  # type: ignore[type-arg]
    weight: float
    id: int
    key: int


class TypedGraphDict(TypedDict):
    directed: bool
    multigraph: bool
    graph: list[GraphDescriptors, GraphDescriptors, GraphDescriptors]  # type: ignore[type-arg]
    nodes: list[TypedNodeDict]
    adjacency: list[list[TypedAdjacencyDict]]


TypedStructureGraphDict = TypedDict(
    "TypedStructureGraphDict",
    {
        "@module": str,
        "@class": str,
        "structure": TypedStructureDict,
        "graphs": TypedGraphDict,
    },
)

TypedMoleculeGraphDict = TypedDict(
    "TypedMoleculeGraphDict",
    {
        "@module": str,
        "@class": str,
        "molecule": TypedMoleculeDict,
        "graphs": TypedGraphDict,
    },
)

StructureGraphTypeVar = TypeVar(
    "StructureGraphTypeVar", StructureGraph, TypedStructureGraphDict
)


MoleculeGraphTypeVar = TypeVar(
    "MoleculeGraphTypeVar", MoleculeGraph, TypedMoleculeGraphDict
)


def pop_empty_structure_graph_keys(sg: StructureGraphTypeVar):
    if isinstance(sg, dict):
        sg["structure"] = pop_empty_structure_keys(sg["structure"])

        return StructureGraph.from_dict(sg)  # type: ignore[arg-type]

    return sg


def pop_empty_molecule_graph_keys(mg: MoleculeGraphTypeVar):
    if isinstance(mg, dict):
        mg["molecule"] = pop_empty_molecule_keys(mg["molecule"])

        return MoleculeGraph.from_dict(mg)  # type: ignore[arg-type]

    return mg


StructureGraphType = Annotated[
    StructureGraphTypeVar,
    BeforeValidator(pop_empty_structure_graph_keys),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedStructureGraphDict
    ),
]

MoleculeGraphType = Annotated[
    MoleculeGraphTypeVar,
    BeforeValidator(pop_empty_molecule_graph_keys),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedMoleculeGraphDict
    ),
]
