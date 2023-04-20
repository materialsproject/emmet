from typing import List
from hashlib import blake2b

from pydantic import Field

from pymatgen.core.periodic_table import Species

from emmet.core.mpid import MPculeID
from emmet.core.qchem.task import TaskDocument
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


class BindingDoc(PropertyDoc):
    """Metal binding properties of a molecule"""

    property_name = "binding"

    metal: str | Species = Field(
        ..., description="The metal bound to the molecule"
    )

    metal_molecule_id: MPculeID = Field(
        ..., description="The MPculeID of the metal atom or ion being bound"
    )

    nometal_molecule_id: MPculeID = Field(
        ..., description="The MPculeID of the molecule with the metal atom/ion removed"
    )

    partial_charge_property_id

    partial_spin_property_id