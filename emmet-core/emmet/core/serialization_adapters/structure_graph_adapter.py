import pymatgen.analysis.graphs
from pydantic import RootModel
from pymatgen.core import Molecule, Structure
from typing_extensions import TypedDict

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
    {"@module": str, "@class": str, "structure": Structure, "graphs": TypedGraphDict},
)

TypedMoleculeGraphDict = TypedDict(
    "TypedMoleculeGraphDict",
    {"@module": str, "@class": str, "molecule": Molecule, "graphs": TypedGraphDict},
)


class StructureGraphAdapter(RootModel):
    root: TypedStructureGraphDict


class MoleculeGraphAdapter(RootModel):
    root: TypedMoleculeGraphDict


setattr(
    pymatgen.analysis.graphs.StructureGraph, "__type_adapter__", StructureGraphAdapter
)
setattr(
    pymatgen.analysis.graphs.MoleculeGraph, "__type_adapter__", MoleculeGraphAdapter
)
