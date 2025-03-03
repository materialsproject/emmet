import pymatgen.analysis.graphs
from pydantic import RootModel
from pymatgen.core import Structure
from typing_extensions import TypedDict

GraphDescriptors = list[str, str]


class TypedNodeDict(TypedDict):
    id: int


class TypedAdjacencyDict(TypedDict):
    to_jimage: list[int, int, int]
    weight: float
    id: int
    key: int


class TypedGraphDict(TypedDict):
    directed: bool
    multigraph: bool
    graph: list[GraphDescriptors, GraphDescriptors, GraphDescriptors]
    nodes: list[TypedNodeDict]
    adjacency: list[list[TypedAdjacencyDict]]


TypedStructureGraphDict = TypedDict(
    "TypedStructureGraphDict",
    {"@module": str, "@class": str, "structure": Structure, "graphs": TypedGraphDict},
)


class StructureGraphAdapter(RootModel):
    root: TypedStructureGraphDict


pymatgen.analysis.graphs.StructureGraph.__pydantic_model__ = StructureGraphAdapter
