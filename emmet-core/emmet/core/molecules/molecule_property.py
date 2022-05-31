""" Core definition of a Materials Document """
from __future__ import annotations

from datetime import datetime
from typing import Sequence, Type, TypeVar, Union, List

from pydantic import Field
from pymatgen.core.structure import Molecule

from emmet.core.material import PropertyOrigin
from emmet.core.mpid import MPID
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
    molecule_id: MPID = Field(
        ...,
        description="The ID of the molecule, used as a universal reference across property documents."
        "This comes in the form of an MPID or int",
    )

    deprecated: bool = Field(
        ...,
        description="Whether this property document is deprecated.",
    )

    deprecation_reasons: List[str] = Field(
        None,
        description="List of deprecation tags detailing why this document isn't valid",
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
        cls: Type[S], meta_molecule: Molecule, molecule_id: MPID, **kwargs
    ) -> S:
        """
        Builds a molecule document using the minimal amount of information
        """

        return super().from_molecule(meta_molecule=meta_molecule, molecule_id=molecule_id, **kwargs)  # type: ignore
