from enum import Enum
from typing import Dict, List, Optional, TypeVar, Union

from pydantic import BaseModel, Field
from pymatgen.core.periodic_table import Element
from pymatgen.core.structure import Structure

from emmet.core.electronic_structure import BandstructureData, DosData
from emmet.core.material_property import PropertyDoc

from emmet.core.mpid import MPID
from emmet.core.thermo import DecompositionProduct
from emmet.core.xas import Edge, Type
from emmet.core.provenance import Database

T = TypeVar("T", bound="SummaryDoc")


class HasProps(Enum):
    """
    Enum of possible hasprops values.
    """

    materials = "materials"
    thermo = "thermo"
    xas = "xas"
    grain_boundaries = "grain_boundaries"
    electronic_structure = "electronic_structure"
    bandstructure = "bandstructure"
    dos = "dos"
    magnetism = "magnetism"
    elasticity = "elasticity"
    dielectric = "dielectric"
    piezoelectric = "piezoelectric"
    surface_properties = "surface_properties"
    oxi_states = "oxi_states"
    provenance = "provenance"
    charge_density = "charge_density"
    eos = "eos"
    phonon = "phonon"
    insertion_electrodes = "insertion_electrodes"
    substrates = "substrates"


class SummaryStats(BaseModel):
    """
    Statistics about a specified SummaryDoc field.
    """

    field: str = Field(
        None,
        title="Field",
        description="Field name corresponding to a field in SummaryDoc.",
    )
    num_samples: Optional[int] = Field(
        None,
        title="Sample",
        description="The number of documents sampled to generate statistics. "
        "If unspecified, statistics will be from entire database.",
    )
    min: float = Field(
        None,
        title="Minimum",
        description="The minimum value " "of the specified field used to " "generate statistics.",
    )
    max: float = Field(
        None,
        title="Maximum",
        description="The maximum value " "of the specified field used to " "generate statistics.",
    )
    median: float = Field(None, title="Median", description="The median of the field values.")
    mean: float = Field(None, title="Mean", description="The mean of the field values.")
    distribution: List[float] = Field(
        None,
        title="Distribution",
        description="List of floats specifying a kernel density "
        "estimator of the distribution, equally spaced "
        "between specified minimum and maximum values.",
    )


class XASSearchData(BaseModel):
    """
    Fields in XAS sub docs in summary
    """

    edge: Edge = Field(
        None,
        title="Absorption Edge",
        description="The interaction edge for XAS",
        source="xas",
    )
    absorbing_element: Element = Field(None, description="Absorbing element.", source="xas")

    spectrum_type: Type = Field(None, description="Type of XAS spectrum.", source="xas")


class GBSearchData(BaseModel):
    """
    Fields in grain boundary sub docs in summary
    """

    sigma: int = Field(None, description="Sigma value of the boundary.", source="grain_boundary")

    type: str = Field(None, description="Grain boundary type.", source="grain_boundary")

    gb_energy: float = Field(None, description="Grain boundary energy in J/m^2.", source="grain_boundary")

    rotation_angle: float = Field(None, description="Rotation angle in degrees.", source="grain_boundary")


class SummaryDoc(PropertyDoc):
    """
    Summary information about materials and their properties, useful for materials
    screening studies and searching.
    """

    property_name = "summary"

    # Materials

    structure: Structure = Field(
        ...,
        description="The lowest energy structure for this material.",
        source="materials",
    )

    task_ids: List[MPID] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs associated with this material.",
        source="materials",
    )

    # Thermo

    uncorrected_energy_per_atom: float = Field(
        None,
        description="The total DFT energy of this material per atom in eV/atom.",
        source="thermo",
    )

    energy_per_atom: float = Field(
        None,
        description="The total corrected DFT energy of this material per atom in eV/atom.",
        source="thermo",
    )

    formation_energy_per_atom: float = Field(
        None,
        description="The formation energy per atom in eV/atom.",
        source="thermo",
    )

    energy_above_hull: float = Field(
        None,
        description="The energy above the hull in eV/Atom.",
        source="thermo",
    )

    is_stable: bool = Field(
        False,
        description="Flag for whether this material is on the hull and therefore stable.",
        source="thermo",
    )

    equilibrium_reaction_energy_per_atom: float = Field(
        None,
        description="The reaction energy of a stable entry from the neighboring equilibrium stable materials in eV."
        " Also known as the inverse distance to hull.",
        source="thermo",
    )

    decomposes_to: List[DecompositionProduct] = Field(
        None,
        description="List of decomposition data for this material. Only valid for metastable or unstable material.",
        source="thermo",
    )

    # XAS

    xas: List[XASSearchData] = Field(None, description="List of xas documents.", source="xas")

    # GB

    grain_boundaries: List[GBSearchData] = Field(
        None,
        description="List of grain boundary documents.",
        source="grain_boundary",
    )

    # Electronic Structure

    band_gap: float = Field(None, description="Band gap energy in eV.", source="electronic_structure")

    cbm: Union[float, Dict] = Field(None, description="Conduction band minimum data.", source="electronic_structure")

    vbm: Union[float, Dict] = Field(None, description="Valence band maximum data.", source="electronic_structure")

    efermi: float = Field(None, description="Fermi energy in eV.", source="electronic_structure")

    is_gap_direct: bool = Field(
        None,
        description="Whether the band gap is direct.",
        source="electronic_structure",
    )

    is_metal: bool = Field(
        None,
        description="Whether the material is a metal.",
        source="electronic_structure",
    )

    es_source_calc_id: Union[MPID, int] = Field(
        None,
        description="The source calculation ID for the electronic structure data.",
        source="electronic_structure",
    )

    bandstructure: BandstructureData = Field(
        None,
        description="Band structure data for the material.",
        source="electronic_structure",
    )

    dos: DosData = Field(
        None,
        description="Density of states data for the material.",
        source="electronic_structure",
    )

    # DOS

    dos_energy_up: float = Field(None, description="Spin-up DOS band gap in eV.", source="electronic_structure")

    dos_energy_down: float = Field(None, description="Spin-down DOS band gap in eV.", source="electronic_structure")

    # Magnetism

    is_magnetic: bool = Field(None, description="Whether the material is magnetic.", source="magnetism")

    ordering: str = Field(None, description="Type of magnetic ordering.", source="magnetism")

    total_magnetization: float = Field(None, description="Total magnetization in μB.", source="magnetism")

    total_magnetization_normalized_vol: float = Field(
        None,
        description="Total magnetization normalized by volume in μB/Å³.",
        source="magnetism",
    )

    total_magnetization_normalized_formula_units: float = Field(
        None,
        description="Total magnetization normalized by formula unit in μB/f.u. .",
        source="magnetism",
    )

    num_magnetic_sites: int = Field(None, description="The number of magnetic sites.", source="magnetism")

    num_unique_magnetic_sites: int = Field(None, description="The number of unique magnetic sites.", source="magnetism")

    types_of_magnetic_species: List[Element] = Field(None, description="Magnetic specie elements.", source="magnetism")

    # Elasticity

    k_voigt: float = Field(None, description="Voigt average of the bulk modulus.")

    k_reuss: float = Field(None, description="Reuss average of the bulk modulus in GPa.")

    k_vrh: float = Field(None, description="Voigt-Reuss-Hill average of the bulk modulus in GPa.")

    g_voigt: float = Field(None, description="Voigt average of the shear modulus in GPa.")

    g_reuss: float = Field(None, description="Reuss average of the shear modulus in GPa.")

    g_vrh: float = Field(None, description="Voigt-Reuss-Hill average of the shear modulus in GPa.")

    universal_anisotropy: float = Field(None, description="Elastic anisotropy.")

    homogeneous_poisson: float = Field(None, description="Poisson's ratio.")

    # Dielectric and Piezo

    e_total: float = Field(None, description="Total dielectric constant.", source="dielectric")

    e_ionic: float = Field(
        None,
        description="Ionic contribution to dielectric constant.",
        source="dielectric",
    )

    e_electronic: float = Field(
        None,
        description="Electronic contribution to dielectric constant.",
        source="dielectric",
    )

    n: float = Field(None, description="Refractive index.", source="dielectric")

    e_ij_max: float = Field(None, description="Piezoelectric modulus.", source="piezoelectric")

    # Surface Properties

    weighted_surface_energy_EV_PER_ANG2: float = Field(
        None,
        description="Weighted surface energy in eV/Å².",
        source="surface_properties",
    )

    weighted_surface_energy: float = Field(
        None,
        description="Weighted surface energy in J/m².",
        source="surface_properties",
    )

    weighted_work_function: float = Field(
        None, description="Weighted work function in eV.", source="surface_properties"
    )

    surface_anisotropy: float = Field(None, description="Surface energy anisotropy.", source="surface_properties")

    shape_factor: float = Field(None, description="Shape factor.", source="surface_properties")

    has_reconstructed: bool = Field(
        None,
        description="Whether the material has any reconstructed surfaces.",
        source="surface_properties",
    )

    # Oxi States

    possible_species: List[str] = Field(
        None,
        description="Possible charged species in this material.",
        source="oxidation_states",
    )

    # Has Props

    has_props: List[HasProps] = Field(
        None,
        description="List of properties that are available for a given material.",
        source="summary",
    )

    # Theoretical

    theoretical: bool = Field(True, description="Whether the material is theoretical.", source="provenance")

    # External Database IDs

    database_IDs: Dict[Database, List[str]] = Field(
        {}, description="External database IDs corresponding to this material."
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
            if doc["dos"] is not None and list(filter(lambda x: x is not None, doc["dos"].values())):
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
    HasProps.provenance.value: ["theoretical", "database_IDs"],
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
                    copy_key: sub_item[copy_key] for copy_key in summary_fields[doc_key] if copy_key in sub_item
                }
                d[doc_key].append(temp_doc)
        elif isinstance(sub_doc, dict):
            d["has_props"].append(doc_key)
            d.update({copy_key: sub_doc[copy_key] for copy_key in summary_fields[doc_key] if copy_key in sub_doc})
    return d
