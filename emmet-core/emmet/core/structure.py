""" Core definition of Structure and Molecule metadata """
from __future__ import annotations

from typing import List, Optional, Type, TypeVar

from pydantic import Field

from pymatgen.core.composition import Composition
from pymatgen.core.periodic_table import Element
from pymatgen.core.structure import Structure, Molecule

from emmet.core.base import EmmetBaseModel
from emmet.core.symmetry import SymmetryData, PointGroupData

T = TypeVar("T", bound="StructureMetadata")
S = TypeVar("S", bound="MoleculeMetadata")


class StructureMetadata(EmmetBaseModel):
    """
    Mix-in class for structure metadata
    """

    # Structure metadata
    nsites: Optional[int] = Field(
        None, description="Total number of sites in the structure."
    )
    elements: Optional[List[Element]] = Field(
        None, description="List of elements in the material."
    )
    nelements: Optional[int] = Field(None, description="Number of elements.")
    composition: Optional[Composition] = Field(
        None, description="Full composition for the material."
    )
    composition_reduced: Optional[Composition] = Field(
        None,
        title="Reduced Composition",
        description="Simplified representation of the composition.",
    )
    formula_pretty: Optional[str] = Field(
        None,
        title="Pretty Formula",
        description="Cleaned representation of the formula.",
    )
    formula_anonymous: Optional[str] = Field(
        None,
        title="Anonymous Formula",
        description="Anonymized representation of the formula.",
    )
    chemsys: Optional[str] = Field(
        None,
        title="Chemical System",
        description="dash-delimited string of elements in the material.",
    )
    volume: Optional[float] = Field(
        None,
        title="Volume",
        description="Total volume for this structure in Angstroms^3.",
    )

    density: Optional[float] = Field(
        None, title="Density", description="Density in grams per cm^3."
    )

    density_atomic: Optional[float] = Field(
        None,
        title="Packing Density",
        description="The atomic packing density in atoms per cm^3.",
    )

    symmetry: Optional[SymmetryData] = Field(
        None, description="Symmetry data for this material."
    )

    @classmethod
    def from_composition(
        cls: Type[T],
        composition: Composition,
        fields: Optional[List[str]] = None,
        **kwargs,
    ) -> T:
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

        elsyms = sorted(set([e.symbol for e in composition.elements]))

        data = {
            "elements": elsyms,
            "nelements": len(elsyms),
            "composition": composition,
            "composition_reduced": composition.reduced_composition.remove_charges(),
            "formula_pretty": composition.reduced_formula,
            "formula_anonymous": composition.anonymized_formula,
            "chemsys": "-".join(elsyms),
        }

        return cls(**{k: v for k, v in data.items() if k in fields}, **kwargs)

    @classmethod
    def from_structure(
        cls: Type[T],
        meta_structure: Structure,
        fields: Optional[List[str]] = None,
        **kwargs,
    ) -> T:
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
        elsyms = sorted(set([e.symbol for e in comp.elements]))
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


class MoleculeMetadata(EmmetBaseModel):
    """
    Mix-in class for molecule metadata
    """

    charge: Optional[int] = Field(None, description="Charge of the molecule")
    spin_multiplicity: Optional[int] = Field(
        None, description="Spin multiplicity of the molecule"
    )
    natoms: Optional[int] = Field(
        None, description="Total number of atoms in the molecule"
    )
    elements: Optional[List[Element]] = Field(
        None, description="List of elements in the molecule"
    )
    nelements: Optional[int] = Field(None, title="Number of Elements")
    nelectrons: Optional[int] = Field(
        None,
        title="Number of electrons",
        description="The total number of electrons for the molecule",
    )
    composition: Optional[Composition] = Field(
        None, description="Full composition for the molecule"
    )
    composition_reduced: Optional[Composition] = Field(
        None,
        title="Reduced Composition",
        description="Simplified representation of the composition",
    )
    formula_alphabetical: Optional[str] = Field(
        None,
        title="Alphabetical Formula",
        description="Alphabetical molecular formula",
    )
    formula_pretty: Optional[str] = Field(
        None,
        title="Pretty Formula",
        description="Cleaned representation of the formula.",
    )
    formula_anonymous: Optional[str] = Field(
        None,
        title="Anonymous Formula",
        description="Anonymized representation of the formula",
    )
    chemsys: Optional[str] = Field(
        None,
        title="Chemical System",
        description="dash-delimited string of elements in the molecule",
    )
    symmetry: Optional[PointGroupData] = Field(
        None, description="Symmetry data for this molecule"
    )

    @classmethod
    def from_composition(
        cls: Type[S],
        comp: Composition,
        fields: Optional[List[str]] = None,
        **kwargs,
    ) -> S:
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

        return cls(**{k: v for k, v in data.items() if k in fields}, **kwargs)

    @classmethod
    def from_molecule(
        cls: Type[S],
        meta_molecule: Molecule,
        fields: Optional[List[str]] = None,
        **kwargs,
    ) -> S:
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
            ]
            if fields is None
            else fields
        )
        comp = meta_molecule.composition
        elsyms = sorted(set([e.symbol for e in comp.elements]))
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

        return cls(**{k: v for k, v in data.items() if k in fields}, **kwargs)
