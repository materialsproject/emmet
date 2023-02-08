""" Core definition of a Materials Document """
from __future__ import annotations

from datetime import datetime
from typing import Sequence, Type, TypeVar, List

from pydantic import Field
from pymatgen.core.structure import Molecule

from emmet.core.qchem.calc_types import LevelOfTheory
from emmet.core.material import PropertyOrigin
from emmet.core.mpid import MPculeID
from emmet.core.structure import MoleculeMetadata


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


S = TypeVar("S", bound="PropertyDoc")


class PropertyDoc(MoleculeMetadata):
    """
    Base model definition for any singular molecule property. This may contain any amount
    of molecule metadata for the purpose of search
    This is intended to be inherited and extended not used directly
    """

    property_name: str

    property_id: str = Field(
        ..., description="The unique identifier of this property document."
    )

    molecule_id: MPculeID = Field(
        ...,
        description="The ID of the molecule, used as a reference across property documents."
        "This comes in the form of an MPculeID (or appropriately formatted string)",
    )

    deprecated: bool = Field(
        ...,
        description="Whether this property document is deprecated.",
    )

    deprecation_reasons: List[str] = Field(
        None,
        description="List of deprecation tags detailing why this document isn't valid",
    )

    level_of_theory: LevelOfTheory = Field(
        None, description="Level of theory used to generate this property document."
    )

    solvent: str = Field(
        None,
        description="String representation of the solvent "
        "environment used to generate this property document.",
    )

    lot_solvent: str = Field(
        None,
        description="String representation of the level of theory and solvent "
        "environment used to generate this property document.",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    origins: Sequence[PropertyOrigin] = Field(
        [], description="Dictionary for tracking the provenance of properties"
    )

    warnings: Sequence[str] = Field(
        [], description="Any warnings related to this property"
    )

    @classmethod
    def from_molecule(  # type: ignore[override]
        cls: Type[S],
        meta_molecule: Molecule,
        property_id: str,
        molecule_id: MPculeID,
        **kwargs
    ) -> S:
        """
        Builds a molecule document using the minimal amount of information
        """

        return super().from_molecule(
            meta_molecule=meta_molecule,
            property_id=property_id,
            molecule_id=molecule_id,
            **kwargs
        )  # type: ignore
