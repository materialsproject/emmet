from hashlib import blake2b
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import Field

from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.molecules.thermo import get_free_energy, ThermoDoc
from emmet.core.mpid import MPID, MPculeID


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


reference_potentials = {"H": 4.44, "Li": 1.40, "Mg": 2.06, "Ca": 1.60}


T = TypeVar("T", bound="RedoxDoc")


class RedoxDoc(PropertyDoc):
    """
    Molecular properties related to reduction and oxidation, including
    vertical ionization energies and electron affinities, as well as reduction
    and oxidation potentials
    """

    property_name = "redox"

    base_property_id: str = Field(description="Property ID for the thermodynamic data of the "
                                              "base molecule")

    electron_affinity: float = Field(None, description="Vertical electron affinity (units: eV)")

    ea_task_id: MPID = Field(None, description="Task ID for the electron affinity calculation")

    ionization_energy: float = Field(None, description="Vertical ionization energy (units: eV)")

    ie_task_id: MPID = Field(None, description="Task ID for the ionization energy calculation")

    reduction_energy: float = Field(
        None, description="Adiabatic electronic energy of reduction (units: eV)"
    )

    reduction_free_energy: float = Field(
        None, description="Adiabatic free energy of reduction (units: eV)"
    )

    red_mpcule_id: MPculeID = Field(None, description="Molecule ID for adiabatic reduction")

    red_property_id: str = Field(None, description="Property ID for the thermodynamic data of the "
                                                   "reduced molecule")

    oxidation_energy: float = Field(
        None, description="Adiabatic electronic energy of oxidation (units: eV)"
    )

    oxidation_free_energy: float = Field(
        None, description="Adiabatic free energy of oxidation (units: eV)"
    )

    ox_mpcule_id: MPculeID = Field(None, description="Molecule ID for adiabatic oxidation")

    ox_property_id: str = Field(None, description="Property ID for the thermodynamic data of the "
                                                  "oxidized molecule")

    reduction_potentials: Dict[str, float] = Field(
        None, description="Reduction potentials with various reference electrodes (units: V)"
    )

    oxidation_potentials: Dict[str, float] = Field(
        None, description="Oxidation potentials with various reference electrodes (units: V)"
    )

    @classmethod
    def _g_or_e(cls: Type[T], entry: Dict[str, Any]) -> float:
        """
        Single atoms may not have free energies like more complex molecules do.
        This function returns the free energy of a TaskDocument entry if
        possible, and otherwise returns the electronic energy.

        :param entry: dict representation of a TaskDocument
        :return:
        """
        try:
            result = get_free_energy(
                entry["output"]["final_energy"], entry["output"]["enthalpy"], entry["output"]["entropy"],
            )
        # Single atoms won't have enthalpy and entropy
        except TypeError:
            result = entry["output"]["final_energy"]

        return result

    @classmethod
    def from_docs(
            cls: Type[T],
            base_molecule_doc: MoleculeDoc,
            base_thermo_doc: ThermoDoc,
            red_doc: Optional[ThermoDoc] = None,
            ox_doc: Optional[ThermoDoc] = None,
            ea_doc: Optional[TaskDocument] = None,
            ie_doc: Optional[TaskDocument] = None,
            deprecated: bool = False,
            **kwargs
    ):  # type: ignore[override]
        """
        Construct a document describing molecular redox properties from
            ThermoDocs (for adiabatic redox potentials and thermodynamics)
            and TaskDocs (for vertical ionization energies and electron
            affinities)

        :param base_molecule_doc: MoleculeDoc of interest
        :param base_thermo_doc: ThermoDoc for the molecule of interest. All properties
            will be calculated in reference to this document
        :param red_doc: ThermoDoc for the reduced molecule. This molecule will
            have the same (covalent) bonding as base_thermo_doc but will differ in
            charge by -1
        :param ox_doc: ThermoDoc for the oxidized molecule. This molecule will
            have the same (covalent) bonding as the base_thermo_doc but will differ
            in charge by +1
        :param ea_doc: A TaskDocument performed at the same structure as
            base_thermo_doc, but at a charge that differs by -1. This document will
            be used to calculate the electron affinity of the molecule
        :param ie_doc: A TaskDocument performed at the same structure as
            base_thermo_doc, but at a charge that differs by +1. This document will
            be used to calculate the ionization energy of the molecule

        :param kwargs: To be passed to PropertyDoc
        :return:
        """

        if all([x is None for x in [red_doc, ox_doc, ea_doc, ie_doc]]):
            # No redox properties can be extracted
            return None

        base_has_g = base_thermo_doc.free_energy is not None

        base_property_id = base_thermo_doc.property_id
        red_mpcule_id = None
        red_property_id = None
        reduction_energy = None
        reduction_free_energy = None
        reduction_potentials = None
        ox_mpcule_id = None
        ox_property_id = None
        oxidation_energy = None
        oxidation_free_energy = None
        oxidation_potentials = None
        ea_task_id = None
        electron_affinity = None
        ie_task_id = None
        ionization_energy = None

        id_string = f"redox-{base_molecule_doc.molecule_id}-{base_thermo_doc.lot_solvent}-" \
                    f"{base_thermo_doc.property_id}"
        origins = list()

        # Adiabatic reduction properties
        if red_doc is not None:
            red_mpcule_id = red_doc.molecule_id
            red_property_id = red_doc.property_id

            id_string += f"-{red_doc.property_id}"

            reduction_energy = red_doc.electronic_energy - base_thermo_doc.electronic_energy

            if base_has_g and red_doc.free_energy is not None:
                reduction_free_energy = red_doc.free_energy - base_thermo_doc.free_energy
            else:
                reduction_free_energy = None

            reduction_potentials = dict()
            for ref, pot in reference_potentials.items():
                # Try to use free energy for redox potentials
                # But if free energy is not available, settle for electronic energy
                red = reduction_free_energy or reduction_energy
                reduction_potentials[ref] = (
                    -1 * red - pot
                )

        # Adiabatic oxidation properties
        if ox_doc is not None:
            ox_mpcule_id = ox_doc.molecule_id
            ox_property_id = ox_doc.property_id

            id_string += f"-{ox_doc.property_id}"

            oxidation_energy = ox_doc.electronic_energy - base_thermo_doc.electronic_energy

            if base_has_g and ox_doc.free_energy is not None:
                oxidation_free_energy = ox_doc.free_energy - base_thermo_doc.free_energy
            else:
                oxidation_free_energy = None

            oxidation_potentials = dict()
            for ref, pot in reference_potentials.items():
                # Try to use free energy for redox potentials
                # But if free energy is not available, settle for electronic energy
                ox = oxidation_free_energy or oxidation_energy
                oxidation_potentials[ref] = (
                    ox - pot
                )

        # Electron affinity
        if ea_doc is not None:
            ea_task_id = ea_doc.task_id
            id_string += f"-{ea_task_id}"
            origins.append(PropertyOrigin(name="electron_affinity", task_id=ea_task_id))
            electron_affinity = ea_doc.output.final_energy * 27.2114 - base_thermo_doc.electronic_energy

        # Ionization energy
        if ie_doc is not None:
            ie_task_id = ie_doc.task_id
            id_string += f"-{ie_task_id}"
            origins.append(PropertyOrigin(name="ionization_energy", task_id=ie_task_id))
            ionization_energy = ie_doc.output.final_energy * 27.2114 - base_thermo_doc.electronic_energy

        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()

        return super().from_molecule(
            meta_molecule=base_molecule_doc.molecule,
            property_id=property_id,
            molecule_id=base_molecule_doc.molecule_id,
            base_property_id=base_property_id,
            level_of_theory=base_thermo_doc.level_of_theory,
            solvent=base_thermo_doc.solvent,
            lot_solvent=base_thermo_doc.lot_solvent,
            red_mpcule_id=red_mpcule_id,
            red_property_id=red_property_id,
            reduction_energy=reduction_energy,
            reduction_free_energy=reduction_free_energy,
            reduction_potentials=reduction_potentials,
            ox_mpcule_id=ox_mpcule_id,
            ox_property_id=ox_property_id,
            oxidation_energy=oxidation_energy,
            oxidation_free_energy=oxidation_free_energy,
            oxidation_potentials=oxidation_potentials,
            ea_task_id=ea_task_id,
            electron_affinity=electron_affinity,
            ie_task_id=ie_task_id,
            ionization_energy=ionization_energy,
            deprecated=deprecated,
            origins=origins,
            **kwargs
        )
