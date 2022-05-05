from enum import Enum
from typing import Dict, List, Tuple, TypeVar, Union

from pydantic import Field
from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph

from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPID
from emmet.core.molecules.orbitals import NaturalPopulation, LonePair, Bond, Interaction


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


T = TypeVar("T", bound="SummaryDoc")


class HasProps(Enum):
    """
    Enum of possible hasprops values.
    """

    molecules = "molecules"
    bonding = "bonding"
    orbitals = "orbitals"
    partial_charges = "partial_charges"
    partial_spins = "partial_spins"
    redox = "redox"
    thermo = "thermo"
    vibration = "vibration"


class SummaryDoc(PropertyDoc):
    """
    Summary information about molecules and their properties, useful for searching.
    """

    property_name = "summary"

    # molecules
    molecule: Molecule = Field(
        ..., description="The lowest energy structure for this molecule"
    )

    task_ids: List[MPID] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculation IDs associated with this molecule.",
    )

    similar_molecules: List[MPID] = Field(
        [], description="IDs associated with similar molecules"
    )

    # thermo
    electronic_energy: float = Field(
        None, description="Electronic energy of the molecule (units: eV)"
    )

    zero_point_energy: float = Field(
        None, description="Zero-point energy of the molecule (units: eV)"
    )

    rt: float = Field(
        None,
        description="R*T, where R is the gas constant and T is temperature, taken "
        "to be 298.15K (units: eV)",
    )

    total_enthalpy: float = Field(
        None, description="Total enthalpy of the molecule at 298.15K (units: eV)"
    )
    total_entropy: float = Field(
        None, description="Total entropy of the molecule at 298.15K (units: eV/K)"
    )

    translational_enthalpy: float = Field(
        None,
        description="Translational enthalpy of the molecule at 298.15K (units: eV)",
    )
    translational_entropy: float = Field(
        None,
        description="Translational entropy of the molecule at 298.15K (units: eV/K)",
    )
    rotational_enthalpy: float = Field(
        None, description="Rotational enthalpy of the molecule at 298.15K (units: eV)"
    )
    rotational_entropy: float = Field(
        None, description="Rotational entropy of the molecule at 298.15K (units: eV/K)"
    )
    vibrational_enthalpy: float = Field(
        None, description="Vibrational enthalpy of the molecule at 298.15K (units: eV)"
    )
    vibrational_entropy: float = Field(
        None, description="Vibrational entropy of the molecule at 298.15K (units: eV/K)"
    )

    free_energy: float = Field(
        None, description="Gibbs free energy of the molecule at 298.15K (units: eV)"
    )

    # vibrational properties
    frequencies: List[float] = Field(
        None, description="List of molecular vibrational frequencies"
    )

    frequency_modes: List[List[List[float]]] = Field(
        None,
        description="Vibrational frequency modes of the molecule (units: Angstrom)",
    )

    ir_intensities: List[float] = Field(
        None,
        title="IR intensities",
        description="Intensities for infrared vibrational spectrum peaks",
    )

    ir_activities: List = Field(
        None,
        title="IR activities",
        description="List indicating if frequency-modes are IR-active",
    )

    # natural bonding orbitals
    open_shell: bool = Field(
        None, description="Is this molecule open-shell (spin multiplicity != 1)?"
    )

    nbo_population: List[NaturalPopulation] = Field(
        None, description="Natural electron populations of the molecule"
    )
    nbo_lone_pairs: List[LonePair] = Field(
        None, description="Lone pair orbitals of a closed-shell molecule"
    )
    nbo_bonds: List[Bond] = Field(
        None, description="Bond-like orbitals of a closed-shell molecule"
    )
    nbo_interactions: List[Interaction] = Field(
        None, description="Orbital-orbital interactions of a closed-shell molecule"
    )

    alpha_population: List[NaturalPopulation] = Field(
        None,
        description="Natural electron populations of the alpha electrons of an "
        "open-shell molecule",
    )
    beta_population: List[NaturalPopulation] = Field(
        None,
        description="Natural electron populations of the beta electrons of an "
        "open-shell molecule",
    )
    alpha_lone_pairs: List[LonePair] = Field(
        None, description="Alpha electron lone pair orbitals of an open-shell molecule"
    )
    beta_lone_pairs: List[LonePair] = Field(
        None, description="Beta electron lone pair orbitals of an open-shell molecule"
    )
    alpha_bonds: List[Bond] = Field(
        None, description="Alpha electron bond-like orbitals of an open-shell molecule"
    )
    beta_bonds: List[Bond] = Field(
        None, description="Beta electron bond-like orbitals of an open-shell molecule"
    )
    alpha_interactions: List[Interaction] = Field(
        None,
        description="Alpha electron orbital-orbital interactions of an open-shell molecule",
    )
    beta_interactions: List[Interaction] = Field(
        None,
        description="Beta electron orbital-orbital interactions of an open-shell molecule",
    )

    # partial charges
    partial_charges: Dict[str, List[float]] = Field(
        None,
        description="Atomic partial charges for the molecule using different partitioning schemes "
        "(Mulliken, Restrained Electrostatic Potential, Natural Bonding Orbitals, etc.)",
    )

    # partial spins
    partial_spins: Dict[str, List[float]] = Field(
        None,
        description="Atomic partial spins for the molecule using different partitioning schemes "
        "(Mulliken, Natural Bonding Orbitals, etc.)",
    )

    # bonding
    molecule_graph: Dict[str, MoleculeGraph] = Field(
        None,
        description="Molecular graph representations of the molecule using different "
        "definitions of bonding.",
    )

    bond_types: Dict[str, Dict[str, List[float]]] = Field(
        description="Dictionaries of bond types to their length under different "
        "definitions of bonding, e.g. C-O to a list of the lengths of "
        "C-O bonds in Angstrom."
    )

    bonds: Dict[str, List[Tuple[int, int]]] = Field(
        description="List of bonds under different definitions of bonding. Each bond takes "
        "the form (a, b), where a and b are 0-indexed atom indices",
    )

    bonds_nometal: Dict[str, List[Tuple[int, int]]] = Field(
        description="List of bonds under different definitions of bonding with all metal ions "
        "removed. Each bond takes the form in the form (a, b), where a and b are "
        "0-indexed atom indices.",
    )

    # redox properties
    electron_affinity: float = Field(
        None, description="Vertical electron affinity in eV"
    )

    ea_id: MPID = Field(None, description="Molecule ID for electron affinity")

    ionization_energy: float = Field(
        None, description="Vertical ionization energy in eV"
    )

    ie_id: MPID = Field(None, description="Molecule ID for ionization energy")

    reduction_free_energy: float = Field(
        None, description="Adiabatic free energy of reduction"
    )

    red_id: MPID = Field(None, description="Molecule ID for adiabatic reduction")

    oxidation_free_energy: float = Field(
        None, description="Adiabatic free energy of oxidation"
    )

    ox_id: MPID = Field(None, description="Molecule ID for adiabatic oxidation")

    reduction_potentials: Dict[str, float] = Field(
        None, description="Reduction potentials with various " "reference electrodes"
    )

    oxidation_potentials: Dict[str, float] = Field(
        None, description="Oxidation potentials with various " "reference electrodes"
    )

    # has props
    has_props: List[HasProps] = Field(
        None, description="List of properties that are available for a given material."
    )

    @classmethod
    def from_docs(cls, molecule_id: MPID, **docs: Dict[str, Union[Dict, List[Dict]]]):
        """Converts a bunch of property docs into a SummaryDoc"""

        doc = _copy_from_doc(docs)
        doc["has_props"] = list(set(doc["has_props"]))

        return SummaryDoc(molecule_id=molecule_id, **doc)


# Key mapping
summary_fields: Dict[str, list] = {
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
        "molecule",
        "deprecated",
        "task_ids",
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
        "ea_id",
        "ionization_energy",
        "ie_id",
        "reduction_free_energy",
        "red_id",
        "oxidation_free_energy",
        "ox_id",
        "reduction_potentials",
        "oxidation_potentials",
    ],
}


def _copy_from_doc(doc):
    """Helper function to copy the list of keys over from amalgamated document"""

    d = {"has_props": []}

    # Function to grab the keys and put them in the root doc
    for doc_key in summary_fields:
        sub_doc = doc.get(doc_key, None)
        if isinstance(sub_doc, list) and len(sub_doc) > 0:
            d["has_props"].append(doc_key)
            for copy_key in summary_fields[doc_key]:
                d[copy_key] = dict()
                for sub_item in sub_doc:
                    # In cases where multiple docs have the same properties,
                    # they must differ by method
                    if copy_key in sub_item and "method" in sub_item:
                        d[copy_key][sub_item["method"]] = sub_item[copy_key]

        elif isinstance(sub_doc, dict):
            d["has_props"].append(doc_key)
            d.update(
                {
                    copy_key: sub_doc[copy_key]
                    for copy_key in summary_fields[doc_key]
                    if copy_key in sub_doc
                }
            )

    return d
