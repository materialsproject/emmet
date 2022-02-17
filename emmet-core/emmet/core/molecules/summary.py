
from enum import Enum
from typing import Dict, List, Optional, Tuple, TypeVar, Union

from pydantic import BaseModel, Field
from pymatgen.core.periodic_table import Element
from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph

from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPID

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
        description="List of Calculations IDs associated with this molecule.",
    )

    similar_molecules: List[MPID] = Field(
        [],
        description="IDs associated with similar molecules"
    )

    # thermo
    electronic_energy: float = Field(
        None,
        description="Electronic energy of the molecule (units: eV)"
    )

    zero_point_energy: float = Field(
        None,
        description="Zero-point energy of the molecule (units: eV)"
    )

    rt: float = Field(
        None,
        description="R*T, where R is the gas constant and T is temperature, taken "
                    "to be 298.15K (units: eV)"
    )

    total_enthalpy: float = Field(
        None,
        description="Total enthalpy of the molecule at 298.15K (units: eV)"
    )
    total_entropy: float = Field(
        None,
        description="Total entropy of the molecule at 298.15K (units: eV/K)"
    )

    translational_enthalpy: float = Field(
        None,
        description="Translational enthalpy of the molecule at 298.15K (units: eV)"
    )
    translational_entropy: float = Field(
        None,
        description="Translational entropy of the molecule at 298.15K (units: eV/K)"
    )
    rotational_enthalpy: float = Field(
        None,
        description="Rotational enthalpy of the molecule at 298.15K (units: eV)"
    )
    rotational_entropy: float = Field(
        None,
        description="Rotational entropy of the molecule at 298.15K (units: eV/K)"
    )
    vibrational_enthalpy: float = Field(
        None,
        description="Vibrational enthalpy of the molecule at 298.15K (units: eV)"
    )
    vibrational_entropy: float = Field(
        None,
        description="Vibrational entropy of the molecule at 298.15K (units: eV/K)"
    )

    free_energy: float = Field(
        None,
        description="Gibbs free energy of the molecule at 298.15K (units: eV)"
    )

    # partial charges
    partial_charges: Dict[str, List[float]] = Field(
        None,
        description="Atomic partial charges for the molecule using different partitioning schemes "
                    "(Mulliken, Restrained Electrostatic Potential, Natural Bonding Orbitals, etc.)"
    )

    # partial spins
    partial_spins: Dict[str, List[float]] = Field(
        None,
        description="Atomic partial spins for the molecule using different partitioning schemes "
                    "(Mulliken, Natural Bonding Orbitals, etc.)"
    )

    # bonding
    molecule_graphs: Dict[str, MoleculeGraph] = Field(
        None,
        description="Molecular graph representations of the molecule using different "
                    "definitions of bonding."
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

    # natural bonding orbitals

    # vibrational properties

    # redox properties

    # has props
    has_props: List[HasProps] = Field(
        None, description="List of properties that are available for a given material."
    )

    @classmethod
    def from_docs(cls, material_id: MPID, **docs: Dict[str, Dict]):
        """Converts a bunch of summary docs into a SummaryDoc"""
        doc = _copy_from_doc(docs)

        # Reshape document for various sub-sections
        # Electronic Structure + Bandstructure + DOS
        if "bandstructure" in doc:
            if doc["bandstructure"] is not None and list(
                filter(lambda x: x is not None, doc["bandstructure"].values())
            ):
                doc["has_props"].append(HasProps.bandstructure.value)
            else:
                del doc["bandstructure"]
        if "dos" in doc:
            if doc["dos"] is not None and list(
                filter(lambda x: x is not None, doc["dos"].values())
            ):
                doc["has_props"].append(HasProps.dos.value)
            else:
                del doc["dos"]
        if "task_id" in doc:
            doc["es_source_calc_id"] = doc["task_id"]
            del doc["task_id"]

        doc["has_props"] = list(set(doc["has_props"]))

        return SummaryDoc(material_id=material_id, **doc)


# Key mapping
summary_fields: Dict[str, list] = {
    HasProps.materials.value: [
        "nsites",
        "elements",
        "nelements",
        "composition",
        "composition_reduced",
        "formula_pretty",
        "formula_anonymous",
        "chemsys",
        "volume",
        "density",
        "density_atomic",
        "symmetry",
        "structure",
        "deprecated",
        "task_ids",
    ],
    HasProps.thermo.value: [
        "uncorrected_energy_per_atom",
        "energy_per_atom",
        "formation_energy_per_atom",
        "energy_above_hull",
        "is_stable",
        "equilibrium_reaction_energy_per_atom",
        "decomposes_to",
    ],
    HasProps.xas.value: ["absorbing_element", "edge", "spectrum_type", "spectrum_id"],
    HasProps.grain_boundaries.value: [
        "gb_energy",
        "sigma",
        "type",
        "rotation_angle",
        "w_sep",
    ],
    HasProps.electronic_structure.value: [
        "band_gap",
        "efermi",
        "cbm",
        "vbm",
        "is_gap_direct",
        "is_metal",
        "bandstructure",
        "dos",
        "task_id",
    ],
    HasProps.magnetism.value: [
        "is_magnetic",
        "ordering",
        "total_magnetization",
        "total_magnetization_normalized_vol",
        "total_magnetization_normalized_formula_units",
        "num_magnetic_sites",
        "num_unique_magnetic_sites",
        "types_of_magnetic_species",
        "is_magnetic",
    ],
    HasProps.elasticity.value: [
        "k_voigt",
        "k_reuss",
        "k_vrh",
        "g_voigt",
        "g_reuss",
        "g_vrh",
        "universal_anisotropy",
        "homogeneous_poisson",
    ],
    HasProps.dielectric.value: ["e_total", "e_ionic", "e_electronic", "n"],
    HasProps.piezoelectric.value: ["e_ij_max"],
    HasProps.surface_properties.value: [
        "weighted_surface_energy",
        "weighted_surface_energy_EV_PER_ANG2",
        "shape_factor",
        "surface_anisotropy",
        "weighted_work_function",
        "has_reconstructed",
    ],
    HasProps.oxi_states.value: ["possible_species"],
    HasProps.provenance.value: ["theoretical"],
    HasProps.charge_density.value: [],
    HasProps.eos.value: [],
    HasProps.phonon.value: [],
    HasProps.insertion_electrodes.value: [],
    HasProps.substrates.value: [],
}


def _copy_from_doc(doc):
    """Helper function to copy the list of keys over from amalgamated document"""
    d = {"has_props": []}
    # Complex function to grab the keys and put them in the root doc
    # if the item is a list, it makes one doc per item with those corresponding keys
    for doc_key in summary_fields:
        sub_doc = doc.get(doc_key, None)
        if isinstance(sub_doc, list) and len(sub_doc) > 0:
            d["has_props"].append(doc_key)
            d[doc_key] = []
            for sub_item in sub_doc:
                temp_doc = {
                    copy_key: sub_item[copy_key]
                    for copy_key in summary_fields[doc_key]
                    if copy_key in sub_item
                }
                d[doc_key].append(temp_doc)
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
