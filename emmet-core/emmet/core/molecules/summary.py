from __future__ import annotations

from enum import Enum
from hashlib import blake2b
from typing import Any, TypeVar

from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.molecules.orbitals import (
    Bond,
    Interaction,
    LonePair,
    NaturalPopulation,
)
from emmet.core.mpid import MPID, MPculeID
from emmet.core.qchem.calc_types import CalcType, LevelOfTheory, TaskType
from pydantic import Field
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.core.structure import Molecule

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


T = TypeVar("T", bound="MoleculeSummaryDoc")


class HasProps(Enum):
    """Enum of possible hasprops values."""

    molecules = "molecules"
    bonding = "bonding"
    orbitals = "orbitals"
    partial_charges = "partial_charges"
    partial_spins = "partial_spins"
    redox = "redox"
    thermo = "thermo"
    vibration = "vibration"


class MoleculeSummaryDoc(PropertyDoc):
    """Summary information about molecules and their properties, useful for searching."""

    property_name = "summary"

    # molecules
    molecules: dict[str, Molecule] = Field(
        ...,
        description="The lowest energy optimized structures for this molecule for each solvent.",
    )

    molecule_levels_of_theory: dict[str, str] = Field(
        None,
        description="Level of theory used to optimize the best molecular structure for each solvent.",
    )

    task_ids: list[MPID] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculation IDs associated with this molecule.",
    )

    similar_molecules: list[MPculeID] = Field(
        [], description="IDs associated with similar molecules"
    )

    constituent_molecules: list[MPculeID] = Field(
        [],
        description="IDs of associated MoleculeDocs used to construct this molecule.",
    )

    unique_calc_types: list[CalcType] = Field(
        None,
        description="Collection of all unique calculation types used for this molecule",
    )

    unique_task_types: list[TaskType] = Field(
        None,
        description="Collection of all unique task types used for this molecule",
    )

    unique_levels_of_theory: list[LevelOfTheory] = Field(
        None,
        description="Collection of all unique levels of theory used for this molecule",
    )

    unique_solvents: list[str] = Field(
        None,
        description="Collection of all unique solvents (solvent parameters) used for this molecule",
    )

    unique_lot_solvents: list[str] = Field(
        None,
        description="Collection of all unique combinations of level of theory and solvent used for this molecule",
    )

    # thermo
    thermo_property_ids: dict[str, str] = Field(
        None,
        description="Solvent:property ID map for each MoleculeThermoDoc for this molecule.",
    )

    thermo_levels_of_theory: dict[str, str] = Field(
        None,
        description="Solvent:level of theory map for each MoleculeThermoDoc for this molecule.",
    )

    electronic_energy: dict[str, float] = Field(
        None, description="Electronic energy of the molecule (units: eV)"
    )

    zero_point_energy: dict[str, float | None] = Field(
        None, description="Zero-point energy of the molecule (units: eV)"
    )

    rt: dict[str, float | None] = Field(
        None,
        description="R*T, where R is the gas constant and T is temperature, taken "
        "to be 298.15K (units: eV)",
    )

    total_enthalpy: dict[str, float | None] = Field(
        None, description="Total enthalpy of the molecule at 298.15K (units: eV)"
    )
    total_entropy: dict[str, float | None] = Field(
        None, description="Total entropy of the molecule at 298.15K (units: eV/K)"
    )

    translational_enthalpy: dict[str, float | None] = Field(
        None,
        description="Translational enthalpy of the molecule at 298.15K (units: eV)",
    )
    translational_entropy: dict[str, float | None] = Field(
        None,
        description="Translational entropy of the molecule at 298.15K (units: eV/K)",
    )
    rotational_enthalpy: dict[str, float | None] = Field(
        None, description="Rotational enthalpy of the molecule at 298.15K (units: eV)"
    )
    rotational_entropy: dict[str, float | None] = Field(
        None, description="Rotational entropy of the molecule at 298.15K (units: eV/K)"
    )
    vibrational_enthalpy: dict[str, float | None] = Field(
        None, description="Vibrational enthalpy of the molecule at 298.15K (units: eV)"
    )
    vibrational_entropy: dict[str, float | None] = Field(
        None, description="Vibrational entropy of the molecule at 298.15K (units: eV/K)"
    )

    free_energy: dict[str, float | None] = Field(
        None, description="Gibbs free energy of the molecule at 298.15K (units: eV)"
    )

    # vibrational properties
    vibration_property_ids: dict[str, str] = Field(
        None,
        description="Solvent:property ID map for each VibrationDoc for this molecule.",
    )

    vibration_levels_of_theory: dict[str, str] = Field(
        None,
        description="Solvent:level of theory map for each VibrationDoc for this molecule.",
    )

    frequencies: dict[str, list[float]] = Field(
        None, description="List of molecular vibrational frequencies"
    )

    frequency_modes: dict[str, list[list[list[float]]]] = Field(
        None,
        description="Vibrational frequency modes of the molecule (units: Angstrom)",
    )

    ir_intensities: dict[str, list[float]] = Field(
        None,
        title="IR intensities",
        description="Intensities for infrared vibrational spectrum peaks",
    )

    ir_activities: dict[str, list] = Field(
        None,
        title="IR activities",
        description="List indicating if frequency-modes are IR-active",
    )

    # natural bonding orbitals
    orbitals_property_ids: dict[str, str] = Field(
        None,
        description="Solvent:property ID map for each OrbitalDoc for this molecule.",
    )

    orbitals_levels_of_theory: dict[str, str] = Field(
        None,
        description="Solvent:level of theory map for each OrbitalDoc for this molecule.",
    )

    open_shell: dict[str, bool] = Field(
        None, description="Is this molecule open-shell (spin multiplicity != 1)?"
    )

    nbo_population: dict[str, list[NaturalPopulation] | None] = Field(
        None, description="Natural electron populations of the molecule"
    )
    nbo_lone_pairs: dict[str, list[LonePair] | None] = Field(
        None, description="Lone pair orbitals of a closed-shell molecule"
    )
    nbo_bonds: dict[str, list[Bond] | None] = Field(
        None, description="Bond-like orbitals of a closed-shell molecule"
    )
    nbo_interactions: dict[str, list[Interaction] | None] = Field(
        None, description="Orbital-orbital interactions of a closed-shell molecule"
    )

    alpha_population: dict[str, list[NaturalPopulation] | None] = Field(
        None,
        description="Natural electron populations of the alpha electrons of an "
        "open-shell molecule",
    )
    beta_population: dict[str, list[NaturalPopulation] | None] = Field(
        None,
        description="Natural electron populations of the beta electrons of an "
        "open-shell molecule",
    )
    alpha_lone_pairs: dict[str, list[LonePair] | None] = Field(
        None, description="Alpha electron lone pair orbitals of an open-shell molecule"
    )
    beta_lone_pairs: dict[str, list[LonePair] | None] = Field(
        None, description="Beta electron lone pair orbitals of an open-shell molecule"
    )
    alpha_bonds: dict[str, list[Bond] | None] = Field(
        None, description="Alpha electron bond-like orbitals of an open-shell molecule"
    )
    beta_bonds: dict[str, list[Bond] | None] = Field(
        None, description="Beta electron bond-like orbitals of an open-shell molecule"
    )
    alpha_interactions: dict[str, list[Interaction] | None] = Field(
        None,
        description="Alpha electron orbital-orbital interactions of an open-shell molecule",
    )
    beta_interactions: dict[str, list[Interaction] | None] = Field(
        None,
        description="Beta electron orbital-orbital interactions of an open-shell molecule",
    )

    # partial charges
    partial_charges_property_ids: dict[str, dict[str, str]] = Field(
        None,
        description="Solvent:method:property ID map for each PartialChargesDoc for this molecule.",
    )

    partial_charges_levels_of_theory: dict[str, dict[str, str]] = Field(
        None,
        description="Solvent:method:level of theory map for each PartialChargesDoc for this molecule.",
    )

    partial_charges: dict[str, dict[str, list[float]]] = Field(
        None,
        description="Atomic partial charges for the molecule using different partitioning schemes "
        "(Mulliken, Restrained Electrostatic Potential, Natural Bonding Orbitals, etc.)",
    )

    # partial spins
    partial_spins_property_ids: dict[str, dict[str, str]] = Field(
        None,
        description="Solvent:method:property ID map for each PartialSpinsDoc for this molecule.",
    )

    partial_spins_levels_of_theory: dict[str, dict[str, str]] = Field(
        None,
        description="Solvent:method:level of theory map for each PartialSpinsDoc for this molecule.",
    )

    partial_spins: dict[str, dict[str, list[float]]] = Field(
        None,
        description="Atomic partial spins for the molecule using different partitioning schemes "
        "(Mulliken, Natural Bonding Orbitals, etc.)",
    )

    # bonding
    bonding_property_ids: dict[str, dict[str, str]] = Field(
        None,
        description="Solvent:method:property ID map for each MoleculeBondingDoc for this molecule.",
    )

    bonding_levels_of_theory: dict[str, dict[str, str]] = Field(
        None,
        description="Solvent:method:level of theory map for each MoleculeBondingDoc for this molecule.",
    )

    molecule_graph: dict[str, dict[str, MoleculeGraph]] = Field(
        None,
        description="Molecular graph representations of the molecule using different "
        "definitions of bonding.",
    )

    bond_types: dict[str, dict[str, dict[str, list[float]]]] = Field(
        None,
        description="Dictionaries of bond types to their length under different "
        "definitions of bonding, e.g. C-O to a list of the lengths of "
        "C-O bonds in Angstrom.",
    )

    bonds: dict[str, dict[str, list[tuple[int, int]]]] = Field(
        None,
        description="List of bonds under different definitions of bonding. Each bond takes "
        "the form (a, b), where a and b are 0-indexed atom indices",
    )

    bonds_nometal: dict[str, dict[str, list[tuple[int, int]]]] = Field(
        None,
        description="List of bonds under different definitions of bonding with all metal ions "
        "removed. Each bond takes the form in the form (a, b), where a and b are "
        "0-indexed atom indices.",
    )

    # redox properties
    redox_property_ids: dict[str, str] = Field(
        None, description="Solvent:property ID map for each RedoxDoc for this molecule."
    )

    redox_levels_of_theory: dict[str, str] = Field(
        None,
        description="Solvent:level of theory map for each RedoxDoc for this molecule.",
    )

    electron_affinity: dict[str, float] = Field(
        None, description="Vertical electron affinity in eV"
    )

    ea_task_id: dict[str, MPID] = Field(
        None, description="Molecule ID for electron affinity"
    )

    ionization_energy: dict[str, float] = Field(
        None, description="Vertical ionization energy in eV"
    )

    ie_task_id: dict[str, MPID] = Field(
        None, description="Molecule ID for ionization energy"
    )

    reduction_free_energy: dict[str, float] = Field(
        None, description="Adiabatic free energy of reduction"
    )

    red_molecule_id: dict[str, MPculeID] = Field(
        None, description="Molecule ID for adiabatic reduction"
    )

    oxidation_free_energy: dict[str, float] = Field(
        None, description="Adiabatic free energy of oxidation"
    )

    ox_molecule_id: dict[str, MPculeID] = Field(
        None, description="Molecule ID for adiabatic oxidation"
    )

    reduction_potentials: dict[str, dict[str, float]] = Field(
        None, description="Reduction potentials with various " "reference electrodes"
    )

    oxidation_potentials: dict[str, dict[str, float]] = Field(
        None, description="Oxidation potentials with various " "reference electrodes"
    )

    # has props
    has_props: list[HasProps] = Field(
        None, description="List of properties that are available for a given material."
    )

    @classmethod
    def from_docs(cls, molecule_id: MPculeID, docs: dict[str, Any]):
        """Converts a bunch of property docs into a SummaryDoc."""
        doc = _copy_from_doc(docs)

        if len(doc["has_props"]) == 0:
            raise ValueError("Missing minimal properties!")

        id_string = f"summary-{molecule_id}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()
        doc["property_id"] = property_id

        doc["has_props"] = list(set(doc["has_props"]))

        return MoleculeSummaryDoc(molecule_id=molecule_id, **doc)


# Key mapping
summary_fields: dict[str, list] = {
    HasProps.molecules.value: [
        "charge",
        "spin_multiplicity",
        "natoms",
        "elements",
        "nelements",
        "composition",
        "formula_alphabetical",
        "chemsys",
        "symmetry",
        "molecules",
        "deprecated",
        "task_ids",
        "unique_calc_types",
        "unique_task_types",
        "unique_levels_of_theory",
        "unique_solvents",
        "unique_lot_solvents",
        "similar_molecules",
        "constituent_molecules",
        "molecule_levels_of_theory",
    ],
    HasProps.thermo.value: [
        "electronic_energy",
        "zero_point_energy",
        "rt",
        "total_enthalpy",
        "total_entropy",
        "translational_enthalpy",
        "translational_entropy",
        "rotational_enthalpy",
        "rotational_entropy",
        "vibrational_enthalpy",
        "vibrational_entropy",
        "free_energy",
    ],
    HasProps.vibration.value: [
        "frequencies",
        "frequency_modes",
        "ir_intensities",
        "ir_activities",
    ],
    HasProps.orbitals.value: [
        "open_shell",
        "nbo_population",
        "nbo_lone_pairs",
        "nbo_bonds",
        "nbo_interactions",
        "alpha_population",
        "beta_population",
        "alpha_lone_pairs",
        "beta_lone_pairs",
        "alpha_bonds",
        "beta_bonds",
        "alpha_interactions",
        "beta_interactions",
    ],
    HasProps.partial_charges.value: ["partial_charges"],
    HasProps.partial_spins.value: ["partial_spins"],
    HasProps.bonding.value: ["molecule_graph", "bond_types", "bonds", "bonds_nometal"],
    HasProps.redox.value: [
        "electron_affinity",
        "ea_task_id",
        "ionization_energy",
        "ie_task_id",
        "reduction_free_energy",
        "red_molecule_id",
        "oxidation_free_energy",
        "ox_molecule_id",
        "reduction_potentials",
        "oxidation_potentials",
    ],
}


def _copy_from_doc(doc: dict[str, Any]):
    """Helper function to copy the list of keys over from amalgamated document."""
    # Doc format:
    # {property0: {...},
    #  property1: {solvent1: {...}, solvent2: {...}},
    #  property2: {solvent1: [{...}, {...}], solvent2: [{...}, {...}]}
    # }

    d: dict[str, Any] = {"has_props": []}

    # Function to grab the keys and put them in the root doc
    for doc_key in summary_fields:
        sub_doc = doc.get(doc_key, None)

        if doc_key == "molecules":
            # Molecules is special because there should only ever be one
            # MoleculeDoc for a given molecule
            # There are not multiple MoleculeDocs for different solvents
            if sub_doc is None:
                break
            for copy_key in summary_fields[doc_key]:
                d[copy_key] = sub_doc[copy_key]
        else:
            sd, by_method = sub_doc

            if isinstance(sd, dict) and len(sd) > 0:
                d["has_props"].append(doc_key)
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
