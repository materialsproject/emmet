from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pymatgen.core import Structure
from pymatgen.core.structure import Molecule
from pymatgen.symmetry.analyzer import (
    PointGroupAnalyzer,
    SpacegroupAnalyzer,
    SymmetryUndeterminedError,
    spglib,
)

from emmet.core.settings import EmmetSettings
from emmet.core.types.enums import ValueEnum

if TYPE_CHECKING:
    from typing import Any

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

    point_group: str | None = Field(
        None, title="Point Group Symbol", description="The point group for the lattice"
    )

    rotation_number: float | None = Field(
        None,
        title="Rotational Symmetry Number",
        description="Rotational symmetry number for the molecule",
    )

    linear: bool | None = Field(
        None, title="Molecule Linearity", description="Is the molecule linear?"
    )

    tolerance: float | None = Field(
        None,
        title="Point Group Analyzer Tolerance",
        description="Distance tolerance to consider sites as symmetrically equivalent.",
    )

    eigen_tolerance: float | None = Field(
        None,
        title="Interia Tensor Eigenvalue Tolerance",
        description="Tolerance to compare eigen values of the inertia tensor.",
    )

    matrix_tolerance: float | None = Field(
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
        symmetry: dict[str, Any] = {
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

    crystal_system: CrystalSystem | None = Field(
        None, title="Crystal System", description="The crystal system for this lattice."
    )

    symbol: str | None = Field(
        None,
        title="Space Group Symbol",
        description="The spacegroup symbol for the lattice.",
    )

    hall: str | None = Field(
        None,
        title="Hall Symbol",
        description="Hall symbol for the lattice",
    )

    number: int | None = Field(
        None,
        title="Space Group Number",
        description="The spacegroup number for the lattice.",
    )

    point_group: str | None = Field(
        None, title="Point Group Symbol", description="The point group for the lattice."
    )

    symprec: float | None = Field(
        None,
        title="Symmetry Finding Precision",
        description="The precision provided to spglib to determine the symmetry of this structure.",
    )

    angle_tolerance: float | None = Field(
        None,
        title="Angle Tolerance",
        description="Angle tolerance provided to spglib to determine the symmetry of this structure.",
    )

    version: str | None = Field(None, title="spglib version")

    @classmethod
    def from_structure(cls, structure: Structure) -> "SymmetryData":
        symmetry: dict[str, Any] = {
            "symbol": None,
            "number": None,
            "point_group": None,
            "crystal_system": None,
            "hall": None,
            "version": spglib.__version__,
            "symprec": SETTINGS.SYMPREC,
            "angle_tolerance": SETTINGS.ANGLE_TOL,
        }

        try:
            sg = SpacegroupAnalyzer(
                structure,
                symprec=symmetry["symprec"],
                angle_tolerance=symmetry["angle_tolerance"],
            )
        except SymmetryUndeterminedError:
            try:
                symmetry["symprec"] = 1e-3
                symmetry["angle_tolerance"] = 1
                sg = SpacegroupAnalyzer(
                    structure,
                    symprec=symmetry["symprec"],
                    angle_tolerance=symmetry["angle_tolerance"],
                )
            except SymmetryUndeterminedError:
                return SymmetryData(**symmetry)

        symmetry.update(
            {
                "symbol": sg.get_space_group_symbol(),
                "number": sg.get_space_group_number(),
                "point_group": sg.get_point_group_symbol(),
                "crystal_system": CrystalSystem(sg.get_crystal_system().title()),
                "hall": sg.get_hall(),
            }
        )

        return SymmetryData(**symmetry)
