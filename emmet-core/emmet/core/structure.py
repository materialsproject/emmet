"""Core definition of Structure and Molecule metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, Field
from pymatgen.core.composition import Composition
from pymatgen.core.structure import Molecule, Structure

from emmet.core.symmetry import PointGroupData, SymmetryData
from emmet.core.types.pymatgen_types.composition_adapter import CompositionType
from emmet.core.types.pymatgen_types.element_adapter import ElementType
from emmet.core.utils import get_graph_hash

if TYPE_CHECKING:
    from typing_extensions import Self

T = TypeVar("T", bound="StructureMetadata")
S = TypeVar("S", bound="MoleculeMetadata")

try:
    from openbabel import openbabel
except Exception:
    openbabel = None


class StructureMetadata(BaseModel):
    """Mix-in class for structure metadata."""

    # Structure metadata
    nsites: int | None = Field(
        None, description="Total number of sites in the structure."
    )
    elements: list[ElementType] | None = Field(
        None, description="List of elements in the material."
    )
    nelements: int | None = Field(None, description="Number of elements.")
    composition: CompositionType | None = Field(
        None, description="Full composition for the material."
    )
    composition_reduced: CompositionType | None = Field(
        None,
        title="Reduced Composition",
        description="Simplified representation of the composition.",
    )
    formula_pretty: str | None = Field(
        None,
        title="Pretty Formula",
        description="Cleaned representation of the formula.",
    )
    formula_anonymous: str | None = Field(
        None,
        title="Anonymous Formula",
        description="Anonymized representation of the formula.",
    )
    chemsys: str | None = Field(
        None,
        title="Chemical System",
        description="dash-delimited string of elements in the material.",
    )
    volume: float | None = Field(
        None,
        title="Volume",
        description="Total volume for this structure in Angstroms^3.",
    )

    density: float | None = Field(
        None, title="Density", description="Density in grams per cm^3."
    )

    density_atomic: float | None = Field(
        None,
        title="Packing Density",
        description="The atomic packing density in atoms per cm^3.",
    )

    symmetry: SymmetryData | None = Field(
        None, description="Symmetry data for this material."
    )

    @classmethod
    def from_composition(
        cls,
        composition: Composition,
        fields: list[str] | None = None,
        **kwargs,
    ) -> Self:
        fields = (
            [
                "elements",
                "nelements",
                "composition",
                "composition_reduced",
                "formula_pretty",
                "formula_anonymous",
                "chemsys",
            ]
            if fields is None
            else fields
        )
        composition = composition.remove_charges()

        elsyms = sorted({e.symbol for e in composition.elements})

        data = {
            "elements": elsyms,
            "nelements": len(elsyms),
            "composition": composition,
            "composition_reduced": composition.reduced_composition.remove_charges(),
            "formula_pretty": composition.reduced_formula,
            "formula_anonymous": composition.anonymized_formula,
            "chemsys": "-".join(elsyms),
        }

        return cls(**{k: v for k, v in data.items() if k in fields}, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_structure(
        cls,
        meta_structure: Structure,
        fields: list[str] | None = None,
        **kwargs,
    ) -> Self:
        fields = (
            [
                "nsites",
                "elements",
                "nelements",
                "composition",
                "composition_reduced",
                "formula_pretty",
                "formula_anonymous",
                "chemsys",
                "volume",
                "density",
                "density_atomic",
                "symmetry",
            ]
            if fields is None
            else fields
        )
        comp = meta_structure.composition.remove_charges()
        elsyms = sorted({e.symbol for e in comp.elements})
        symmetry = SymmetryData.from_structure(meta_structure)

        data = {
            "nsites": meta_structure.num_sites,
            "elements": elsyms,
            "nelements": len(elsyms),
            "composition": comp,
            "composition_reduced": comp.reduced_composition,
            "formula_pretty": comp.reduced_formula,
            "formula_anonymous": comp.anonymized_formula,
            "chemsys": "-".join(elsyms),
            "volume": meta_structure.volume,
            "density": meta_structure.density,
            "density_atomic": meta_structure.volume / meta_structure.num_sites,
            "symmetry": symmetry,
        }
        kwargs.update({k: v for k, v in data.items() if k in fields})
        return cls(**kwargs)


class MoleculeMetadata(BaseModel):
    """Mix-in class for molecule metadata."""

    charge: int | None = Field(None, description="Charge of the molecule")
    spin_multiplicity: int | None = Field(
        None, description="Spin multiplicity of the molecule"
    )
    natoms: int | None = Field(
        None, description="Total number of atoms in the molecule"
    )
    elements: list[ElementType] | None = Field(
        None, description="List of elements in the molecule"
    )
    nelements: int | None = Field(None, title="Number of Elements")
    nelectrons: int | None = Field(
        None,
        title="Number of electrons",
        description="The total number of electrons for the molecule",
    )
    composition: CompositionType | None = Field(
        None, description="Full composition for the molecule"
    )
    composition_reduced: CompositionType | None = Field(
        None,
        title="Reduced Composition",
        description="Simplified representation of the composition",
    )
    formula_alphabetical: str | None = Field(
        None,
        title="Alphabetical Formula",
        description="Alphabetical molecular formula",
    )
    formula_pretty: str | None = Field(
        None,
        title="Pretty Formula",
        description="Cleaned representation of the formula.",
    )
    formula_anonymous: str | None = Field(
        None,
        title="Anonymous Formula",
        description="Anonymized representation of the formula",
    )
    chemsys: str | None = Field(
        None,
        title="Chemical System",
        description="dash-delimited string of elements in the molecule",
    )
    symmetry: PointGroupData | None = Field(
        None, description="Symmetry data for this molecule"
    )
    species_hash: str | None = Field(
        None,
        description="Weisfeiler Lehman (WL) graph hash using the atom species as the graph "
        "node attribute.",
    )
    coord_hash: str | None = Field(
        None,
        description="Weisfeiler Lehman (WL) graph hash using the atom coordinates as the graph "
        "node attribute.",
    )

    @classmethod
    def from_composition(
        cls,
        comp: Composition,
        fields: list[str] | None = None,
        **kwargs,
    ) -> Self:
        """
        Create a MoleculeMetadata model from a composition.

        Parameters
        ----------
        comp : .Composition
            A pymatgen composition.
        fields : list of str or None
            Composition fields to include.
        **kwargs
            Keyword arguments that are passed to the model constructor.

        Returns
        -------
        T
            A molecule metadata model.
        """
        fields = (
            [
                "elements",
                "nelements",
                "composition",
                "composition_reduced",
                "formula_alphabetical",
                "formula_pretty",
                "formula_anonymous",
                "chemsys",
            ]
            if fields is None
            else fields
        )
        elsyms = sorted({e.symbol for e in comp.elements})

        data = {
            "elements": elsyms,
            "nelements": len(elsyms),
            "composition": comp,
            "composition_reduced": comp.reduced_composition,
            "formula_alphabetical": comp.alphabetical_formula,
            "formula_pretty": comp.reduced_formula,
            "formula_anonymous": comp.anonymized_formula,
            "chemsys": "-".join(elsyms),
        }

        return cls(**{k: v for k, v in data.items() if k in fields}, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_molecule(
        cls,
        meta_molecule: Molecule,
        fields: list[str] | None = None,
        **kwargs,
    ) -> Self:
        fields = (
            [
                "charge",
                "spin_multiplicity",
                "natoms",
                "elements",
                "nelements",
                "nelectrons",
                "composition",
                "composition_reduced",
                "formula_alphabetical",
                "formula_pretty",
                "formula_anonymous",
                "chemsys",
                "symmetry",
                "species_hash",
                "coord_hash",
            ]
            if fields is None
            else fields
        )
        comp = meta_molecule.composition
        elsyms = sorted({e.symbol for e in comp.elements})
        symmetry = PointGroupData.from_molecule(meta_molecule)

        data = {
            "charge": int(meta_molecule.charge),
            "spin_multiplicity": meta_molecule.spin_multiplicity,
            "natoms": len(meta_molecule),
            "elements": elsyms,
            "nelements": len(elsyms),
            "nelectrons": int(meta_molecule.nelectrons),
            "composition": comp,
            "composition_reduced": comp.reduced_composition,
            "formula_alphabetical": comp.alphabetical_formula,
            "formula_pretty": comp.reduced_formula,
            "formula_anonymous": comp.anonymized_formula,
            "chemsys": "-".join(elsyms),
            "symmetry": symmetry,
        }
        if openbabel:
            data["species_hash"] = get_graph_hash(meta_molecule, "specie")
            data["coord_hash"] = get_graph_hash(meta_molecule, "coords")

        return cls(**{k: v for k, v in data.items() if k in fields}, **kwargs)
