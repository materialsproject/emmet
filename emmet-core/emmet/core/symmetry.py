from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from pymatgen.core import Structure
from pymatgen.core.structure import Molecule
from pymatgen.symmetry.analyzer import PointGroupAnalyzer, SpacegroupAnalyzer, spglib

from emmet.core.settings import EmmetSettings
from emmet.core.utils import ValueEnum

SETTINGS = EmmetSettings()


class CrystalSystem(ValueEnum):
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


class PointGroupData(BaseModel):
    """
    Defines symmetry for a molecule document
    """

    point_group: Optional[str] = Field(
        None, title="Point Group Symbol", description="The point group for the lattice"
    )

    rotation_number: Optional[float] = Field(
        None,
        title="Rotational Symmetry Number",
        description="Rotational symmetry number for the molecule",
    )

    linear: Optional[bool] = Field(
        None, title="Molecule Linearity", description="Is the molecule linear?"
    )

    tolerance: Optional[float] = Field(
        None,
        title="Point Group Analyzer Tolerance",
        description="Distance tolerance to consider sites as symmetrically equivalent.",
    )

    eigen_tolerance: Optional[float] = Field(
        None,
        title="Interia Tensor Eigenvalue Tolerance",
        description="Tolerance to compare eigen values of the inertia tensor.",
    )

    matrix_tolerance: Optional[float] = Field(
        None,
        title="Symmetry Operation Matrix Element Tolerance",
        description="Tolerance used to generate the full set of symmetry operations of the point group.",
    )

    @classmethod
    def from_molecule(cls, molecule: Molecule) -> "PointGroupData":
        tol = SETTINGS.PGATOL
        eigentol = SETTINGS.PGAEIGENTOL
        matrixtol = SETTINGS.PGAMATRIXTOL
        pga = PointGroupAnalyzer(
            molecule,
            tolerance=tol,
            eigen_tolerance=eigentol,
            matrix_tolerance=matrixtol,
        )
        symmetry: Dict[str, Any] = {
            "tolerance": tol,
            "eigen_tolerance": eigentol,
            "matrix_tolerance": matrixtol,
            "point_group": pga.sch_symbol,
        }

        rotational_symmetry_numbers = {
            1.0: ["C1", "Cs", "Ci", "C*v", "S2"],
            2.0: ["C2", "C2h", "C2v", "S4", "D*h"],
            3.0: ["C3", "C3h", "C3v", "S6"],
            4.0: ["C4v", "D4h", "D4d", "D2", "D2h", "D2d"],
            5.0: ["C5v", "Ih"],
            6.0: ["D3", "D3h", "D3d"],
            10.0: ["D5h", "D5d"],
            12.0: ["T", "Td", "Th", "D6h"],
            14.0: ["D7h"],
            16.0: ["D8h"],
            24.0: ["Oh"],
            float("inf"): ["Kh"],
        }

        r = 1.0
        for rot_num, point_groups in rotational_symmetry_numbers.items():
            if symmetry["point_group"] in point_groups:
                r = rot_num
                break
        if symmetry["point_group"] in ["C*v", "D*h"]:
            linear = True
        else:
            linear = False

        symmetry["rotation_number"] = float(r)
        symmetry["linear"] = linear

        return PointGroupData(**symmetry)


class SymmetryData(BaseModel):
    """
    Defines a symmetry data set for materials documents
    """

    crystal_system: Optional[CrystalSystem] = Field(
        None, title="Crystal System", description="The crystal system for this lattice."
    )

    symbol: Optional[str] = Field(
        None,
        title="Space Group Symbol",
        description="The spacegroup symbol for the lattice.",
    )

    number: Optional[int] = Field(
        None,
        title="Space Group Number",
        description="The spacegroup number for the lattice.",
    )

    point_group: Optional[str] = Field(
        None, title="Point Group Symbol", description="The point group for the lattice."
    )

    symprec: Optional[float] = Field(
        None,
        title="Symmetry Finding Precision",
        description="The precision given to spglib to determine the symmetry of this lattice.",
    )

    version: Optional[str] = Field(None, title="SPGLib version")

    @classmethod
    def from_structure(cls, structure: Structure) -> "SymmetryData":
        symprec = SETTINGS.SYMPREC
        sg = SpacegroupAnalyzer(structure, symprec=symprec)
        symmetry: Dict[str, Any] = {"symprec": symprec}
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
                "version": spglib.__version__,
            }
        )

        return SymmetryData(**symmetry)
