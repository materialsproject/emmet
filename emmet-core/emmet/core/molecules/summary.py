from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TypeVar
from hashlib import blake2b

from pydantic import Field
from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph

from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPID, MPculeID
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

    species: List[str] = Field(
        None, description="Ordered list of elements/species in this Molecule."
    )

    task_ids: List[MPID] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculation IDs associated with this molecule.",
    )

    similar_molecules: List[MPculeID] = Field(
        [], description="IDs associated with similar molecules"
    )

    # thermo
    electronic_energy: Dict[str, float] = Field(
        None, description="Electronic energy of the molecule (units: eV)"
    )

    zero_point_energy: Dict[str, Optional[float]] = Field(
        None, description="Zero-point energy of the molecule (units: eV)"
    )

    rt: Dict[str, Optional[float]] = Field(
        None,
        description="R*T, where R is the gas constant and T is temperature, taken "
        "to be 298.15K (units: eV)",
    )

    total_enthalpy: Dict[str, Optional[float]] = Field(
        None, description="Total enthalpy of the molecule at 298.15K (units: eV)"
    )
    total_entropy: Dict[str, Optional[float]] = Field(
        None, description="Total entropy of the molecule at 298.15K (units: eV/K)"
    )

    translational_enthalpy: Dict[str, Optional[float]] = Field(
        None,
        description="Translational enthalpy of the molecule at 298.15K (units: eV)",
    )
    translational_entropy: Dict[str, Optional[float]] = Field(
        None,
        description="Translational entropy of the molecule at 298.15K (units: eV/K)",
    )
    rotational_enthalpy: Dict[str, Optional[float]] = Field(
        None, description="Rotational enthalpy of the molecule at 298.15K (units: eV)"
    )
    rotational_entropy: Dict[str, Optional[float]] = Field(
        None, description="Rotational entropy of the molecule at 298.15K (units: eV/K)"
    )
    vibrational_enthalpy: Dict[str, Optional[float]] = Field(
        None, description="Vibrational enthalpy of the molecule at 298.15K (units: eV)"
    )
    vibrational_entropy: Dict[str, Optional[float]] = Field(
        None, description="Vibrational entropy of the molecule at 298.15K (units: eV/K)"
    )

    free_energy: Dict[str, Optional[float]] = Field(
        None, description="Gibbs free energy of the molecule at 298.15K (units: eV)"
    )

    # vibrational properties
    frequencies: Dict[str, List[float]] = Field(
        None, description="List of molecular vibrational frequencies"
    )

    frequency_modes: Dict[str, List[List[List[float]]]] = Field(
        None,
        description="Vibrational frequency modes of the molecule (units: Angstrom)",
    )

    ir_intensities: Dict[str, List[float]] = Field(
        None,
        title="IR intensities",
        description="Intensities for infrared vibrational spectrum peaks",
    )

    ir_activities: Dict[str, List] = Field(
        None,
        title="IR activities",
        description="List indicating if frequency-modes are IR-active",
    )

    # natural bonding orbitals
    open_shell: Dict[str, bool] = Field(
        None, description="Is this molecule open-shell (spin multiplicity != 1)?"
    )

    nbo_population: Dict[str, Optional[List[NaturalPopulation]]] = Field(
        None, description="Natural electron populations of the molecule"
    )
    nbo_lone_pairs: Dict[str, Optional[List[LonePair]]] = Field(
        None, description="Lone pair orbitals of a closed-shell molecule"
    )
    nbo_bonds: Dict[str, Optional[List[Bond]]] = Field(
        None, description="Bond-like orbitals of a closed-shell molecule"
    )
    nbo_interactions: Dict[str, Optional[List[Interaction]]] = Field(
        None, description="Orbital-orbital interactions of a closed-shell molecule"
    )

    alpha_population: Dict[str, Optional[List[NaturalPopulation]]] = Field(
        None,
        description="Natural electron populations of the alpha electrons of an "
        "open-shell molecule",
    )
    beta_population: Dict[str, Optional[List[NaturalPopulation]]] = Field(
        None,
        description="Natural electron populations of the beta electrons of an "
        "open-shell molecule",
    )
    alpha_lone_pairs: Dict[str, Optional[List[LonePair]]] = Field(
        None, description="Alpha electron lone pair orbitals of an open-shell molecule"
    )
    beta_lone_pairs: Dict[str, Optional[List[LonePair]]] = Field(
        None, description="Beta electron lone pair orbitals of an open-shell molecule"
    )
    alpha_bonds: Dict[str, Optional[List[Bond]]] = Field(
        None, description="Alpha electron bond-like orbitals of an open-shell molecule"
    )
    beta_bonds: Dict[str, Optional[List[Bond]]] = Field(
        None, description="Beta electron bond-like orbitals of an open-shell molecule"
    )
    alpha_interactions: Dict[str, Optional[List[Interaction]]] = Field(
        None,
        description="Alpha electron orbital-orbital interactions of an open-shell molecule",
    )
    beta_interactions: Dict[str, Optional[List[Interaction]]] = Field(
        None,
        description="Beta electron orbital-orbital interactions of an open-shell molecule",
    )

    # partial charges
    partial_charges: Dict[str, Dict[str, List[float]]] = Field(
        None,
        description="Atomic partial charges for the molecule using different partitioning schemes "
        "(Mulliken, Restrained Electrostatic Potential, Natural Bonding Orbitals, etc.)",
    )

    # partial spins
    partial_spins: Dict[str, Dict[str, List[float]]] = Field(
        None,
        description="Atomic partial spins for the molecule using different partitioning schemes "
        "(Mulliken, Natural Bonding Orbitals, etc.)",
    )

    # bonding
    molecule_graph: Dict[str, Dict[str, MoleculeGraph]] = Field(
        None,
        description="Molecular graph representations of the molecule using different "
        "definitions of bonding.",
    )

    bond_types: Dict[str, Dict[str, Dict[str, List[float]]]] = Field(
        None,
        description="Dictionaries of bond types to their length under different "
        "definitions of bonding, e.g. C-O to a list of the lengths of "
        "C-O bonds in Angstrom.",
    )

    bonds: Dict[str, Dict[str, List[Tuple[int, int]]]] = Field(
        None,
        description="List of bonds under different definitions of bonding. Each bond takes "
        "the form (a, b), where a and b are 0-indexed atom indices",
    )

    bonds_nometal: Dict[str, Dict[str, List[Tuple[int, int]]]] = Field(
        None,
        description="List of bonds under different definitions of bonding with all metal ions "
        "removed. Each bond takes the form in the form (a, b), where a and b are "
        "0-indexed atom indices.",
    )

    # redox properties
    electron_affinity: Dict[str, float] = Field(
        None, description="Vertical electron affinity in eV"
    )

    ea_task_id: Dict[str, MPID] = Field(None, description="Molecule ID for electron affinity")

    ionization_energy: Dict[str, float] = Field(
        None, description="Vertical ionization energy in eV"
    )

    ie_task_id: Dict[str, MPID] = Field(None, description="Molecule ID for ionization energy")

    reduction_free_energy: Dict[str, float] = Field(
        None, description="Adiabatic free energy of reduction"
    )

    red_mpcule_id: Dict[str, MPculeID] = Field(None, description="Molecule ID for adiabatic reduction")

    oxidation_free_energy: Dict[str, float] = Field(
        None, description="Adiabatic free energy of oxidation"
    )

    ox_mpcule_id: Dict[str, MPculeID] = Field(None, description="Molecule ID for adiabatic oxidation")

    reduction_potentials: Dict[str, Dict[str, float]] = Field(
        None, description="Reduction potentials with various " "reference electrodes"
    )

    oxidation_potentials: Dict[str, Dict[str, float]] = Field(
        None, description="Oxidation potentials with various " "reference electrodes"
    )

    # has props
    has_props: List[HasProps] = Field(
        None, description="List of properties that are available for a given material."
    )

    @classmethod
    def from_docs(
        cls,
        molecule_id: MPculeID,
        docs: Dict[str, Any]
    ):
        """Converts a bunch of property docs into a SummaryDoc"""

        doc = _copy_from_doc(docs)

        if len(doc["has_props"]) == 0:
            raise ValueError("Missing minimal properties!")

        id_string = f"summary-{molecule_id}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()
        doc["property_id"] = property_id

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
        "species",
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
        "ea_task_id",
        "ionization_energy",
        "ie_task_id",
        "reduction_free_energy",
        "red_mpcule_id",
        "oxidation_free_energy",
        "ox_mpcule_id",
        "reduction_potentials",
        "oxidation_potentials",
    ],
}


def _copy_from_doc(doc: Dict[str, Any]):
    """Helper function to copy the list of keys over from amalgamated document"""

    # Doc format:
    # {property0: {...},
    #  property1: {solvent1: {...}, solvent2: {...}},
    #  property2: {solvent1: [{...}, {...}], solvent2: [{...}, {...}]}
    # }

    d: Dict[str, Any] = {"has_props": []}

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
                                if entry.get(copy_key):
                                    d[copy_key][solvent][method] = entry[copy_key]
                            if len(d[copy_key][solvent]) == 0:
                                # If this key was not populated at all for this solvent, get rid of it
                                del d[copy_key][solvent]
                    else:
                        for solvent, entry in sd.items():
                            if entry.get(copy_key):
                                d[copy_key][solvent] = entry[copy_key]

                    if len(d[copy_key]) == 0:
                        # If this key was not populated at all, set it to None
                        d[copy_key] = None

    return d
