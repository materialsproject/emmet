from hashlib import blake2b
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import Field

from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.molecules.thermo import get_free_energy, MoleculeThermoDoc
from emmet.core.mpid import MPID, MPculeID


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


reference_potential = 4.44


T = TypeVar("T", bound="RedoxDoc")


class RedoxDoc(PropertyDoc):
    """
    Molecular properties related to reduction and oxidation, including
    vertical ionization energies and electron affinities, as well as reduction
    and oxidation potentials
    """

    property_name: str = "redox"

    base_property_id: str = Field(
        description="Property ID for the thermodynamic data of the " "base molecule"
    )

    electron_affinity: Optional[float] = Field(
        None, description="Vertical electron affinity (units: eV)"
    )

    ea_task_id: Optional[MPID] = Field(
        None, description="Task ID for the electron affinity calculation"
    )

    ionization_energy: Optional[float] = Field(
        None, description="Vertical ionization energy (units: eV)"
    )

    ie_task_id: Optional[MPID] = Field(
        None, description="Task ID for the ionization energy calculation"
    )

    reduction_energy: Optional[float] = Field(
        None, description="Adiabatic electronic energy of reduction (units: eV)"
    )

    reduction_free_energy: Optional[float] = Field(
        None, description="Adiabatic free energy of reduction (units: eV)"
    )

    red_molecule_id: Optional[MPculeID] = Field(
        None, description="Molecule ID for adiabatic reduction"
    )

    red_property_id: Optional[str] = Field(
        None,
        description="Property ID for the thermodynamic data of the " "reduced molecule",
    )

    oxidation_energy: Optional[float] = Field(
        None, description="Adiabatic electronic energy of oxidation (units: eV)"
    )

    oxidation_free_energy: Optional[float] = Field(
        None, description="Adiabatic free energy of oxidation (units: eV)"
    )

    ox_molecule_id: Optional[MPculeID] = Field(
        None, description="Molecule ID for adiabatic oxidation"
    )

    ox_property_id: Optional[str] = Field(
        None,
        description="Property ID for the thermodynamic data of the "
        "oxidized molecule",
    )

    reduction_potential: Optional[float] = Field(
        None,
        description="Reduction potential referenced to the standard hydrogen electrode (SHE) (units: V)",
    )

    oxidation_potential: Optional[float] = Field(
        None,
        description="Oxidation potential referenced to the standard hydrogen electrode (SHE) (units: V)",
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
                entry["output"]["final_energy"],
                entry["output"]["enthalpy"],
                entry["output"]["entropy"],
            )
        # Single atoms won't have enthalpy and entropy
        except TypeError:
            result = entry["output"]["final_energy"]

        return result

    @classmethod
    def from_docs(
        cls: Type[T],
        base_molecule_doc: MoleculeDoc,
        base_thermo_doc: MoleculeThermoDoc,
        red_doc: Optional[MoleculeThermoDoc] = None,
        ox_doc: Optional[MoleculeThermoDoc] = None,
        ea_doc: Optional[TaskDocument] = None,
        ie_doc: Optional[TaskDocument] = None,
        deprecated: bool = False,
        **kwargs,
    ):  # type: ignore[override]
        """
        Construct a document describing molecular redox properties from
            MoleculeThermoDocs (for adiabatic redox potentials and thermodynamics)
            and TaskDocs (for vertical ionization energies and electron
            affinities)

        :param base_molecule_doc: MoleculeDoc of interest
        :param base_thermo_doc: MoleculeThermoDoc for the molecule of interest. All properties
            will be calculated in reference to this document
        :param red_doc: MoleculeThermoDoc for the reduced molecule. This molecule will
            have the same (covalent) bonding as base_thermo_doc but will differ in
            charge by -1
        :param ox_doc: MoleculeThermoDoc for the oxidized molecule. This molecule will
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
        red_molecule_id = None
        red_property_id = None
        reduction_energy = None
        reduction_free_energy = None
        reduction_potential = None
        ox_molecule_id = None
        ox_property_id = None
        oxidation_energy = None
        oxidation_free_energy = None
        oxidation_potential = None
        ea_task_id = None
        electron_affinity = None
        ie_task_id = None
        ionization_energy = None

        id_string = (
            f"redox-{base_molecule_doc.molecule_id}-{base_thermo_doc.lot_solvent}-"
            f"{base_thermo_doc.property_id}"
        )
        origins = list()

        # Adiabatic reduction properties
        if red_doc is not None:
            red_molecule_id = red_doc.molecule_id
            red_property_id = red_doc.property_id

            id_string += f"-{red_doc.property_id}"

            reduction_energy = (
                red_doc.electronic_energy - base_thermo_doc.electronic_energy
            )

            if base_has_g and red_doc.free_energy is not None:
                reduction_free_energy = (
                    red_doc.free_energy - base_thermo_doc.free_energy
                )
            else:
                reduction_free_energy = None

            red = reduction_free_energy or reduction_energy
            reduction_potential = -1 * red - reference_potential

        # Adiabatic oxidation properties
        if ox_doc is not None:
            ox_molecule_id = ox_doc.molecule_id
            ox_property_id = ox_doc.property_id

            id_string += f"-{ox_doc.property_id}"

            oxidation_energy = (
                ox_doc.electronic_energy - base_thermo_doc.electronic_energy
            )

            if base_has_g and ox_doc.free_energy is not None:
                oxidation_free_energy = ox_doc.free_energy - base_thermo_doc.free_energy
            else:
                oxidation_free_energy = None

            ox = oxidation_free_energy or oxidation_energy
            oxidation_potential = ox - reference_potential

        # Electron affinity
        if ea_doc is not None:
            ea_task_id = ea_doc.task_id
            id_string += f"-{ea_task_id}"
            origins.append(PropertyOrigin(name="electron_affinity", task_id=ea_task_id))
            electron_affinity = (
                ea_doc.output.final_energy * 27.2114 - base_thermo_doc.electronic_energy
            )

        # Ionization energy
        if ie_doc is not None:
            ie_task_id = ie_doc.task_id
            id_string += f"-{ie_task_id}"
            origins.append(PropertyOrigin(name="ionization_energy", task_id=ie_task_id))
            ionization_energy = (
                ie_doc.output.final_energy * 27.2114 - base_thermo_doc.electronic_energy
            )

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
            red_molecule_id=red_molecule_id,
            red_property_id=red_property_id,
            reduction_energy=reduction_energy,
            reduction_free_energy=reduction_free_energy,
            reduction_potential=reduction_potential,
            ox_molecule_id=ox_molecule_id,
            ox_property_id=ox_property_id,
            oxidation_energy=oxidation_energy,
            oxidation_free_energy=oxidation_free_energy,
            oxidation_potential=oxidation_potential,
            ea_task_id=ea_task_id,
            electron_affinity=electron_affinity,
            ie_task_id=ie_task_id,
            ionization_energy=ionization_energy,
            deprecated=deprecated,
            origins=origins,
            **kwargs,
        )
