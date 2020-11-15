""" Core definitions of Molecules metadata """

from typing import (
    Optional,
    Type,
    TypeVar,
    List,
)

from pydantic import BaseModel, Field
from pymatgen.core.periodic_table import Element
from pymatgen.io.babel import BabelMolAdaptor
from pymatgen.symmetry.analyzer import PointGroupAnalyzer

from emmet.stubs import Composition, Molecule


T = TypeVar("T", bound="MoleculeMetadata")


class MoleculeMetadata(BaseModel):
    """
    Mix-in class for molecule metadata
    """

    # Molecule metadata
    nsites: int = Field(None, description="Total number of sites in the molecule")

    elements: List[Element] = Field(
        None, description="List of elements in the molecule"
    )

    nelements: int = Field(None, title="Number of Elements")

    composition: Composition = Field(
        None, description="Full composition for the molecule"
    )

    formula_pretty: str = Field(
        None,
        title="Pretty Formula",
        description="Cleaned representation of the chemical formula",
    )

    formula_alphabetical: str = Field(
        None,
        title="Alphabetical Formula",
        description="Alphebetized version of chemical the formula",
    )

    formula_anonymous: str = Field(
        None,
        title="Anonymous Formula",
        description="Anonymized representation of the formula",
    )

    chemsys: str = Field(
        None,
        title="Chemical System",
        description="Dash-delimited string of elements in the molecule",
    )

    molecular_weight: float = Field(
        None,
        title="Molecular Weight",
        description="Molecular weight of this Molecule, in g/mol",
    )

    smiles: str = Field(
        None,
        title="SMILES string",
        description="Simplified molecular-input line-entry system (SMILES) string",
    )

    canonical_smiles: str = Field(
        None,
        title="Canonical SMILES string",
        description="Unambiguous and canonical SMILES representation",
    )

    inchi: str = Field(
        None,
        title="InChI",
        description="IUPAC international chemical identifier string",
    )

    point_group: str = Field(
        None, title="Point Group Symbol", description="The point group for the lattice"
    )

    @classmethod
    def from_composition(
        cls: Type[T],
        composition: Composition,
        fields: Optional[List[str]] = None,
        **kwargs
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
                "molecular_weight",
            ]
            if fields is None
            else fields
        )
        elsyms = sorted(set([e.symbol for e in composition.elements]))

        data = {
            "elements": elsyms,
            "nelements": len(elsyms),
            "composition": composition,
            "composition_reduced": composition.reduced_composition,
            "formula_pretty": composition.reduced_formula,
            "formula_anonymous": composition.anonymized_formula,
            "formula_alphabetical": composition.alphabetical_formula,
            "chemsys": "-".join(elsyms),
            "molecular_weight": composition.weight,
        }

        return cls(**{k: v for k, v in data.items() if k in fields}, **kwargs)

    @classmethod
    def from_molecule(
        cls: Type[T],
        molecule: Molecule,
        fields: Optional[List[str]] = None,
        include_molecule: bool = False,
        **kwargs
    ) -> T:

        fields = (
            [
                "nsites",
                "elements",
                "nelements",
                "composition",
                "formula_pretty",
                "formula_anonymous",
                "formula_alphabetical",
                "chemsys",
                "molecular_weight",
                "smiles",
                "canonical_smiles" "inchi",
                "point_group",
            ]
            if fields is None
            else fields
        )
        comp = molecule.composition
        bb = BabelMolAdaptor(molecule)
        pbmol = bb.pybel_mol
        pga = PointGroupAnalyzer(molecule)
        elsyms = sorted(set([e.symbol for e in comp.elements]))

        data = {
            "nsites": molecule.num_sites,
            "elements": elsyms,
            "nelements": len(elsyms),
            "composition": comp,
            "formula_pretty": comp.reduced_formula,
            "formula_anonymous": comp.anonymized_formula,
            "formula_alphabetical": comp.alphabetical_formula,
            "chemsys": "-".join(elsyms),
            "molecular_weight": comp.weight,
            "smiles": pbmol.write(str("smi")).split()[0],
            "canonical_smiles": pbmol.write(str("can")).split()[0],
            "inchi": pbmol.write(str("inchi")).strip(),
            "point_group": pga.sch_symbol,
        }

        if include_molecule:
            kwargs.update({"molecule": molecule})

        return cls(**{k: v for k, v in data.items() if k in fields}, **kwargs)
