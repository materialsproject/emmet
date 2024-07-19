from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TypeVar
from hashlib import blake2b

from pydantic import BaseModel, Field
from pymatgen.core.structure import Molecule

from emmet.core.qchem.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPID, MPculeID
from emmet.core.molecules.metal_binding import MetalBindingData


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


T = TypeVar("T", bound="MoleculeSummaryDoc")


class HasProps(Enum):
    """
    Enum of possible hasprops values.
    """

    molecules = "molecules"
    bonding = "bonding"
    forces = "forces"
    metal_binding = "metal_binding"
    multipole_moments = "multipole_moments"
    orbitals = "orbitals"
    partial_charges = "partial_charges"
    partial_spins = "partial_spins"
    redox = "redox"
    thermo = "thermo"
    vibration = "vibration"


class ThermoComposite(BaseModel):
    """
    Summary information obtained from MoleculeThermoDocs
    """
    
    property_id: Optional[str] = Field(
        None,
        description="Property ID map for this MoleculeThermoDoc",
    )

    level_of_theory: Optional[str] = Field(
        None,
        description="Level of theory for this MoleculeThermoDoc.",
    )

    electronic_energy: Optional[float] = Field(
        None, description="Electronic energy of the molecule (units: eV)"
    )

    zero_point_energy: Optional[float] = Field(
        None, description="Zero-point energy of the molecule (units: eV)"
    )

    total_enthalpy: Optional[float] = Field(
        None, description="Total enthalpy of the molecule at 298.15K (units: eV)"
    )
    total_entropy: Optional[float] = Field(
        None, description="Total entropy of the molecule at 298.15K (units: eV/K)"
    )

    free_energy: Optional[float] = Field(
        None, description="Gibbs free energy of the molecule at 298.15K (units: eV)"
    )


class VibrationComposite(BaseModel):
    """
    Summary information obtained from VibrationDocs
    """
    
    property_id: Optional[str] = Field(
        None,
        description="Property ID for this VibrationDoc.",
    )

    level_of_theory: Optional[str] = Field(
        None,
        description="Level of theory for this VibrationDoc.",
    )

    frequencies: Optional[List[float]] = Field(
        None, description="List of molecular vibrational frequencies"
    )


class OrbitalComposite(BaseModel):
    """
    Summary information obtained from OrbitalDocs
    """
    
    orbitals_property_ids: Optional[str] = Field(
        None,
        description="Property ID for this OrbitalDoc.",
    )

    level_of_theory: Optional[str] = Field(
        None,
        description="Level of theory for this OrbitalDoc.",
    )

    open_shell: Optional[bool] = Field(
        None, description="Is this molecule open-shell (spin multiplicity != 1)?"
    )


class PartialChargesComposite(BaseModel):
    """
    Summary information obtained from PartialChargesDocs
    """

    property_id: Optional[str] = Field(
        None,
        description="Property ID for this PartialChargesDoc.",
    )

    level_of_theory: Optional[str] = Field(
        None,
        description="Level of theory for this PartialChargesDoc.",
    )

    partial_charges: Optional[List[float]] = Field(
        None,
        description="Atomic partial charges for the molecule",
    )


class PartialSpinsComposite(BaseModel):
    """
    Summary information obtained from PartialSpinsDocs
    """

    property_id: Optional[str] = Field(
        None,
        description="Property ID for this PartialSpinsDoc.",
    )

    level_of_theory: Optional[str] = Field(
        None,
        description="Level of theory for this PartialSpinsDoc.",
    )

    partial_spins: Optional[List[float]] = Field(
        None,
        description="Atomic partial spins for the molecule",
    )


class BondingComposite(BaseModel):
    """
    Summary information obtained from MoleculeBondingDocs
    """

    property_id: Optional[str] = Field(
        None,
        description="Property ID for this MoleculeBondingDoc.",
    )

    level_of_theory: Optional[str] = Field(
        None,
        description="Level of theory for this MoleculeBondingDoc.",
    )

    bond_types: Optional[Dict[str, List[float]]] = Field(
        None,
        description="Dictionaries of bond types to their length, e.g. C-O to a list of the lengths of C-O bonds in "
        "Angstrom.",
    )

    bonds: Optional[List[Tuple[int, int]]] = Field(
        None,
        description="List of bonds. Each bond takes the form (a, b), where a and b are 0-indexed atom indices",
    )

    bonds_nometal: Optional[List[Tuple[int, int]]] = Field(
        None,
        description="List of bonds with all metal ions removed. Each bond takes the form in the form (a, b), where a "
        "and b are 0-indexed atom indices.",
    )


class MultipolesComposite(BaseModel):
    """
    Summary information obtained from ElectricMultipoleDocs
    """

    property_id: Optional[str] = Field(
        None,
        description="Property ID for this ElectricMultipoleDoc.",
    )

    level_of_theory: Optional[str] = Field(
        None,
        description="Level of theory for this ElectricMultipoleDoc.",
    )

    total_dipole: Optional[float] = Field(
        None,
        description="Total molecular dipole moment (Debye)",
    )

    resp_total_dipole: Optional[float] = Field(
        None,
        description="Total dipole moment, calculated via restrained electrostatic potential (RESP) (Debye)",
    )


class RedoxComposite(BaseModel):
    """
    Summary information obtained from RedoxDocs
    """

    property_id: Optional[str] = Field(
        None, description="Property ID for this RedoxDoc."
    )

    level_of_theory: Optional[str] = Field(
        None,
        description="Level of theory for this RedoxDoc.",
    )

    electron_affinity: Optional[float] = Field(
        None, description="Vertical electron affinity in eV"
    )

    ea_task_id: Optional[MPID] = Field(
        None, description="Molecule ID for electron affinity"
    )

    ionization_energy: Optional[float] = Field(
        None, description="Vertical ionization energy in eV"
    )

    ie_task_id: Optional[MPID] = Field(
        None, description="Molecule ID for ionization energy"
    )

    reduction_free_energy: Optional[float] = Field(
        None, description="Adiabatic free energy of reduction"
    )

    red_molecule_id: Optional[MPculeID] = Field(
        None, description="Molecule ID for adiabatic reduction"
    )

    oxidation_free_energy: Optional[float] = Field(
        None, description="Adiabatic free energy of oxidation"
    )

    ox_molecule_id: Optional[MPculeID] = Field(
        None, description="Molecule ID for adiabatic oxidation"
    )

    reduction_potential: Optional[float] = Field(
        None,
        description="Reduction potential referenced to the standard hydrogen electrode (SHE) (units: V)",
    )

    oxidation_potential: Optional[float] = Field(
        None,
        description="Oxidation potential referenced to the standard hydrogen electrode (SHE) (units: V)",
    )


class MetalBindingComposite(BaseModel):
    """
    Summary information obtained from MetalBindingDocs
    """

    partial_charges_property_id: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="ID of PartialChargesDoc used to estimate metal charge",
    )

    partial_spins_property_id: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="ID of PartialSpinsDoc used to estimate metal spin",
    )

    partial_charges_lot_solvent: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="Combination of level of theory and solvent used to calculate atomic partial charges",
    )

    partial_spins_lot_solvent: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="Combination of level of theory and solvent used to calculate atomic partial spins",
    )

    charge_spin_method: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="The method used for partial charges and spins (must be the same).",
    )

    bonding_property_id: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="ID of MoleculeBondingDoc used to detect bonding in this molecule",
    )

    bonding_lot_solvent: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="Combination of level of theory and solvent used to determine the coordination environment "
        "of the metal atom or ion",
    )

    bonding_method: Optional[Dict[str, Dict[str, str]]] = Field(
        None, description="The method used for to define bonding."
    )

    thermo_property_id: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="ID of MoleculeThermoDoc used to obtain this molecule's thermochemistry",
    )

    thermo_lot_solvent: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="Combination of level of theory and solvent used for uncorrected thermochemistry",
    )

    thermo_correction_lot_solvent: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="Combination of level of theory and solvent used to correct the electronic energy",
    )

    thermo_combined_lot_solvent: Optional[Dict[str, Dict[str, str]]] = Field(
        None,
        description="Combination of level of theory and solvent used for molecular thermochemistry, combining "
        "both the frequency calculation and (potentially) the single-point energy correction.",
    )

    binding_data: Optional[Dict[str, Dict[str, List[MetalBindingData]]]] = Field(
        None, description="Binding data for each metal atom or ion in the molecule"
    )


class MoleculeSummaryDoc(PropertyDoc):
    """
    Summary information about molecules and their properties, useful for searching.
    """

    property_name: str = "summary"

    # molecules
    molecules: Dict[str, Molecule] = Field(
        ...,
        description="The lowest energy optimized structures for this molecule for each solvent.",
    )

    molecule_levels_of_theory: Optional[Dict[str, str]] = Field(
        None,
        description="Level of theory used to optimize the best molecular structure for each solvent.",
    )

    species_hash: Optional[str] = Field(
        None,
        description="Weisfeiler Lehman (WL) graph hash using the atom species as the graph "
        "node attribute.",
    )
    coord_hash: Optional[str] = Field(
        None,
        description="Weisfeiler Lehman (WL) graph hash using the atom coordinates as the graph "
        "node attribute.",
    )

    inchi: Optional[str] = Field(
        None, description="International Chemical Identifier (InChI) for this molecule"
    )
    inchi_key: Optional[str] = Field(
        None, description="Standardized hash of the InChI for this molecule"
    )

    task_ids: List[MPID] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculation IDs associated with this molecule.",
    )

    similar_molecules: List[MPculeID] = Field(
        [], description="IDs associated with similar molecules"
    )

    constituent_molecules: List[MPculeID] = Field(
        [],
        description="IDs of associated MoleculeDocs used to construct this molecule.",
    )

    unique_calc_types: Optional[List[CalcType]] = Field(
        None,
        description="Collection of all unique calculation types used for this molecule",
    )

    unique_task_types: Optional[List[TaskType]] = Field(
        None,
        description="Collection of all unique task types used for this molecule",
    )

    unique_levels_of_theory: Optional[List[LevelOfTheory]] = Field(
        None,
        description="Collection of all unique levels of theory used for this molecule",
    )

    unique_solvents: Optional[List[str]] = Field(
        None,
        description="Collection of all unique solvents (solvent parameters) used for this molecule",
    )

    unique_lot_solvents: Optional[List[str]] = Field(
        None,
        description="Collection of all unique combinations of level of theory and solvent used for this molecule",
    )

    # Properties

    thermo: Optional[Dict[str, ThermoComposite]] = Field(
        None,
        description="A summary of thermodynamic data available for this molecule, organized by solvent"
    )

    vibrations: Optional[Dict[str, VibrationComposite]] = Field(
        None,
        description="A summary of the vibrational data available for this molecule, organized by solvent"
    )

    orbitals: Optional[Dict[str, OrbitalComposite]] = Field(
        None,
        description="A summary of the orbital (NBO) data available for this molecule, organized by solvent"
    )

    partial_charges: Optional[Dict[str, Dict[str, PartialChargesComposite]]] = Field(
        None,
        description="A summary of the partial charge data available for this molecule, organized by solvent and by "
                    "method"
    )

    partial_spins: Optional[Dict[str, Dict[str, PartialSpinsComposite]]] = Field(
        None,
        description="A summary of the partial spin data available for this molecule, organized by solvent and by "
                    "method"
    )

    bonding: Optional[Dict[str, Dict[str, BondingComposite]]] = Field(
        None,
        description="A summary of the bonding data available for this molecule, organized by solvent and by method"
    )

    multipoles: Optional[Dict[str, MultipolesComposite]] = Field(
        None,
        description="A summary of the electric multipole data available for this molecule, organized by solvent"
    )

    redox: Optional[Dict[str, RedoxComposite]] = Field(
        None,
        description="A summary of the redox data available for this molecule, organized by solvent"
    )

    metal_binding: Optional[Dict[str, Dict[str, MetalBindingComposite]]] = Field(
        None,
        description="A summary of the metal binding data available for this molecule, organized by solvent and by "
                    "method"
    )

    # has props
    has_props: Optional[Dict[str, bool]] = Field(
        None,
        description="Properties available for this molecule",
    )

    @classmethod
    def from_docs(cls, molecule_id: MPculeID, docs: Dict[str, Any]):
        """Converts a bunch of property docs into a SummaryDoc"""

        doc = _copy_from_doc(docs)

        if len(doc["has_props"]) == 0:
            raise ValueError("Missing minimal properties!")

        id_string = f"summary-{molecule_id}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()
        doc["property_id"] = property_id

        return MoleculeSummaryDoc(molecule_id=molecule_id, **doc)


# Key mapping
summary_fields: Dict[str, list] = {
    HasProps.molecules.value: [
        "charge",
        "spin_multiplicity",
        "natoms",
        "elements",
        "nelements",
        "composition",
        "composition_reduced",
        "formula_alphabetical",
        "chemsys",
        "symmetry",
        "molecules",
        "deprecated",
        "task_ids",
        "species_hash",
        "coord_hash",
        "inchi",
        "inchi_key",
        "unique_calc_types",
        "unique_task_types",
        "unique_levels_of_theory",
        "unique_solvents",
        "unique_lot_solvents",
        "similar_molecules",
        "constituent_molecules",
        "molecule_levels_of_theory",
    ],
    HasProps.forces.value: [],
    HasProps.thermo.value: [
        "electronic_energy",
        "zero_point_energy",
        "total_enthalpy",
        "total_entropy",
        "free_energy",
    ],
    HasProps.vibration.value: [
        "frequencies",
    ],
    HasProps.orbitals.value: [
        "open_shell",
    ],
    HasProps.partial_charges.value: ["partial_charges"],
    HasProps.partial_spins.value: ["partial_spins"],
    HasProps.bonding.value: ["bond_types", "bonds", "bonds_nometal"],
    HasProps.multipole_moments.value: [
        "total_dipole",
        "resp_total_dipole",
    ],
    HasProps.redox.value: [
        "electron_affinity",
        "ea_task_id",
        "ionization_energy",
        "ie_task_id",
        "reduction_free_energy",
        "red_molecule_id",
        "oxidation_free_energy",
        "ox_molecule_id",
        "reduction_potential",
        "oxidation_potential",
    ],
    HasProps.metal_binding.value: [
        "binding_partial_charges_property_id",
        "binding_partial_spins_property_id",
        "binding_partial_charges_lot_solvent",
        "binding_partial_spins_lot_solvent",
        "binding_charge_spin_method",
        "binding_bonding_property_id",
        "binding_bonding_lot_solvent",
        "binding_bonding_method",
        "binding_thermo_property_id",
        "binding_thermo_lot_solvent",
        "binding_thermo_correction_lot_solvent",
        "binding_thermo_combined_lot_solvent",
        "binding_data",
    ],
}


# TODO: you are here

def _copy_from_doc(doc: Dict[str, Any]):
    """Helper function to copy the list of keys over from amalgamated document"""

    # Doc format:
    # {property0: {...},
    #  property1: {solvent1: {...}, solvent2: {...}},
    #  property2: {solvent1: [{...}, {...}], solvent2: [{...}, {...}]}
    # }

    has_props: Dict[str, bool] = {str(val.value): False for val in HasProps}
    d: Dict[str, Any] = {"has_props": has_props, "origins": []}

    # Function to grab the keys and put them in the root doc
    for doc_key in summary_fields:
        sub_doc = doc.get(doc_key, None)

        if doc_key == "molecules":
            # Molecules is special because there should only ever be one
            # MoleculeDoc for a given molecule
            # There are not multiple MoleculeDocs for different solvents
            if sub_doc is None:
                break

            d["has_props"][doc_key] = True
            for copy_key in summary_fields[doc_key]:
                d[copy_key] = sub_doc[copy_key]
        else:
            # No information for this particular set of properties
            # Shouldn't happen, but can
            if sub_doc is None:
                continue

            d["has_props"][doc_key] = True
            sd, by_method = sub_doc

            if isinstance(sd, dict) and len(sd) > 0:
                for copy_key in summary_fields[doc_key]:
                    d[copy_key] = dict()

                    if by_method:
                        for solvent, solv_entries in sd.items():
                            d[copy_key][solvent] = dict()
                            for method, entry in solv_entries.items():
                                if entry.get(copy_key) is not None:
                                    d[copy_key][solvent][method] = entry[copy_key]
                            if len(d[copy_key][solvent]) == 0:
                                # If this key was not populated at all for this solvent, get rid of it
                                del d[copy_key][solvent]
                    else:
                        for solvent, entry in sd.items():
                            if entry.get(copy_key) is not None:
                                d[copy_key][solvent] = entry[copy_key]

                    if len(d[copy_key]) == 0:
                        # If this key was not populated at all, set it to None
                        d[copy_key] = None

                # Populate property id and level of theory values
                d[doc_key + "_property_ids"] = dict()
                d[doc_key + "_levels_of_theory"] = dict()
                if by_method:
                    for solvent, solv_entries in sd.items():
                        d[doc_key + "_property_ids"][solvent] = dict()
                        d[doc_key + "_levels_of_theory"][solvent] = dict()
                        for method, entry in solv_entries.items():
                            d[doc_key + "_property_ids"][solvent][method] = entry[
                                "property_id"
                            ]
                            d[doc_key + "_levels_of_theory"][solvent][method] = entry[
                                "level_of_theory"
                            ]
                        if len(d[doc_key + "_property_ids"][solvent]) == 0:
                            del d[doc_key + "_property_ids"][solvent]
                        if len(d[doc_key + "_levels_of_theory"][solvent]) == 0:
                            del d[doc_key + "_levels_of_theory"][solvent]

                else:
                    for solvent, entry in sd.items():
                        d[doc_key + "_property_ids"][solvent] = entry["property_id"]
                        d[doc_key + "_levels_of_theory"][solvent] = entry[
                            "level_of_theory"
                        ]

                if len(d[doc_key + "_property_ids"]) == 0:
                    d[doc_key + "_property_ids"] = None
                if len(d[doc_key + "_levels_of_theory"]) == 0:
                    d[doc_key + "_levels_of_theory"] = None

    return d
