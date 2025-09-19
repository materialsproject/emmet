from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.analysis.graphs import MoleculeGraph, StructureGraph
from typing_extensions import TypedDict

from emmet.core.types.pymatgen_types.structure_adapter import (
    TypedMoleculeDict,
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


def pop_empty_graph_keys(graph: StructureGraphTypeVar | MoleculeGraphTypeVar):
    if isinstance(graph, dict):
        target_cls: type[StructureGraph | MoleculeGraph]
        match graph["@class"]:
            case "StructureGraph":
                target_cls = StructureGraph
                graph["structure"] = pop_empty_structure_keys(graph["structure"])  # type: ignore[typeddict-unknown-key, typeddict-item]
            case "MoleculeGraph":
                target_cls = MoleculeGraph
                graph["molecule"] = pop_empty_structure_keys(graph["molecule"])  # type: ignore[typeddict-unknown-key, typeddict-item]

        return target_cls.from_dict(graph)  # type: ignore[arg-type]

    return graph


StructureGraphType = Annotated[
    StructureGraphTypeVar,
    BeforeValidator(pop_empty_graph_keys),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedStructureGraphDict
    ),
]

MoleculeGraphType = Annotated[
    MoleculeGraphTypeVar,
    BeforeValidator(pop_empty_graph_keys),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedMoleculeGraphDict
    ),
]
