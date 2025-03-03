import pymatgen.analysis.defects.core
from pydantic import RootModel
from pymatgen.core import Site, Structure
from typing_extensions import TypedDict

TypedDefectDict = TypedDict(
    "TypedDefectDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "structure": Structure,
        "site": Site,
        "multiplicity": int,
        "oxi_state": float,
        "equivalent_sites": list[Site],
        "symprec": float,
        "angle_tolerance": float,
        "user_changes": list[int],
    },
)


class DefectAdapter(RootModel):
    root: TypedDefectDict


pymatgen.analysis.defects.core.Defect.__pydantic_model__ = DefectAdapter
