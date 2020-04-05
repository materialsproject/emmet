from enum import Enum
from pydantic import BaseModel, Field

from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.core import SETTINGS
from emmet.stubs import Structure


class CrystalSystem(Enum):
    """
    The crystal system of the lattice
    """

    tri = "Triclinic"
    mono = "Monoclinic"
    ortho = "Orthorhombic"
    tet = "Tetragonal"
    trig = "Trigonal"
    hex_ = "Hexagonal"
    cubic = "Cubic"


class SymmetryData(BaseModel):
    """
    Defines a symmetry data set for materials documents
    """

    crystal_system: CrystalSystem = Field(
        None, title="Crystal System", description="The crystal system for this lattice"
    )

    symbol: str = Field(
        None,
        title="Space Group Symbol",
        description="The spacegroup symbol for the lattice",
    )

    number: int = Field(
        None,
        title="Space Group Number",
        description="The spacegroup number for the lattice",
    )

    point_group: str = Field(
        None, title="Point Group Symbol", description="The point group for the lattice"
    )

    symprec: float = Field(
        None,
        title="Symmetry Finding Precision",
        description="The precision given to spglib to determine the symmetry of this lattice",
    )

    version: str = Field(None, title="SPGLib version")

    @classmethod
    def from_structure(cls, structure: Structure) -> "SymmetryData":
        symprec = SETTINGS.SYMPREC
        sg = SpacegroupAnalyzer(structure, symprec=symprec)
        symmetry = {"symprec": symprec}
        if not sg.get_symmetry_dataset():
            sg = SpacegroupAnalyzer(structure, 1e-3, 1)
            symmetry["symprec"] = 1e-3

        symmetry.update(
            {
                "source": "spglib",
                "symbol": sg.get_space_group_symbol(),
                "number": sg.get_space_group_number(),
                "point_group": sg.get_point_group_symbol(),
                "crystal_system": CrystalSystem(sg.get_crystal_system().title()),
                "hall": sg.get_hall(),
            }
        )

        return SymmetryData(**symmetry)
