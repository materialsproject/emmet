from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from emmet.core.electronic_structure import BandstructureData, DosData
from emmet.core.material_property import PropertyDoc
from emmet.core.thermo import DecompositionProduct
from emmet.core.types.enums import ValueEnum, XasEdge, XasType
from emmet.core.types.pymatgen_types.element_adapter import ElementType
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.types.typing import IdentifierType

if TYPE_CHECKING:
    from typing_extensions import Self


class HasProps(ValueEnum):
    """
    Enum of possible hasprops values.
    """

    materials = "materials"
    thermo = "thermo"
    xas = "xas"
    grain_boundaries = "grain_boundaries"
    chemenv = "chemenv"
    electronic_structure = "electronic_structure"
    absorption = "absorption"
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

    field: str | None = Field(
        None,
        title="Field",
        description="Field name corresponding to a field in SummaryDoc.",
    )
    num_samples: int | None = Field(
        None,
        title="Sample",
        description="The number of documents sampled to generate statistics. "
        "If unspecified, statistics will be from entire database.",
    )
    min: float | None = Field(
        None,
        title="Minimum",
        description="The minimum value "
        "of the specified field used to "
        "generate statistics.",
    )
    max: float | None = Field(
        None,
        title="Maximum",
        description="The maximum value "
        "of the specified field used to "
        "generate statistics.",
    )
    median: float | None = Field(
        None, title="Median", description="The median of the field values."
    )
    mean: float | None = Field(
        None, title="Mean", description="The mean of the field values."
    )
    distribution: list[float] | None = Field(
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

    edge: XasEdge | None = Field(
        None,
        title="Absorption Edge",
        description="The interaction edge for XAS",
    )
    absorbing_element: ElementType | None = Field(
        None,
        description="Absorbing element.",
    )

    spectrum_type: XasType | None = Field(
        None,
        description="Type of XAS spectrum.",
    )


class GBSearchData(BaseModel):
    """
    Fields in grain boundary sub docs in summary
    """

    sigma: int | None = Field(
        None,
        description="Sigma value of the boundary.",
    )

    type: str | None = Field(
        None,
        description="Grain boundary type.",
    )

    gb_energy: float | None = Field(
        None,
        description="Grain boundary energy in J/m^2.",
    )

    rotation_angle: float | None = Field(
        None,
        description="Rotation angle in degrees.",
    )


class SummaryDoc(PropertyDoc):
    """
    Summary information about materials and their properties, useful for materials
    screening studies and searching.
    """

    property_name: str = "summary"

    # Materials
    task_ids: list[IdentifierType] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs associated with this material.",
    )

    structure: StructureType = Field(
        ...,
        description="The lowest energy structure for this material.",
    )

    # Thermo

    uncorrected_energy_per_atom: float | None = Field(
        None,
        description="The total DFT energy of this material per atom in eV/atom.",
    )

    energy_per_atom: float | None = Field(
        None,
        description="The total corrected DFT energy of this material per atom in eV/atom.",
    )

    formation_energy_per_atom: float | None = Field(
        None,
        description="The formation energy per atom in eV/atom.",
    )

    energy_above_hull: float | None = Field(
        None,
        description="The energy above the hull in eV/Atom.",
    )

    is_stable: bool = Field(
        False,
        description="Flag for whether this material is on the hull and therefore stable.",
    )

    equilibrium_reaction_energy_per_atom: float | None = Field(
        None,
        description="The reaction energy of a stable entry from the neighboring equilibrium stable materials in eV."
        " Also known as the inverse distance to hull.",
    )

    decomposes_to: list[DecompositionProduct] | None = Field(
        None,
        description="List of decomposition data for this material. Only valid for metastable or unstable material.",
    )

    # XAS

    xas: list[XASSearchData] | None = Field(
        None,
        description="List of xas documents.",
    )

    # GB

    grain_boundaries: list[GBSearchData] | None = Field(
        None,
        description="List of grain boundary documents.",
    )

    # Electronic Structure

    band_gap: float | None = Field(
        None,
        description="Band gap energy in eV.",
    )

    cbm: float | None = Field(
        None,
        description="Conduction band minimum data.",
    )

    vbm: float | None = Field(
        None,
        description="Valence band maximum data.",
    )

    efermi: float | None = Field(
        None,
        description="Fermi energy in eV.",
    )

    is_gap_direct: bool | None = Field(
        None,
        description="Whether the band gap is direct.",
    )

    is_metal: bool | None = Field(
        None,
        description="Whether the material is a metal.",
    )

    es_source_calc_id: IdentifierType | None = Field(
        None,
        description="The source calculation ID for the electronic structure data.",
    )

    bandstructure: BandstructureData | None = Field(
        None,
        description="Band structure data for the material.",
    )

    dos: DosData | None = Field(
        None,
        description="Density of states data for the material.",
    )

    # DOS

    dos_energy_up: float | None = Field(
        None,
        description="Spin-up DOS band gap in eV.",
    )

    dos_energy_down: float | None = Field(
        None,
        description="Spin-down DOS band gap in eV.",
    )

    # Magnetism

    is_magnetic: bool | None = Field(
        None,
        description="Whether the material is magnetic.",
    )

    ordering: str | None = Field(
        None,
        description="Type of magnetic ordering.",
    )

    total_magnetization: float | None = Field(
        None,
        description="Total magnetization in μB.",
    )

    total_magnetization_normalized_vol: float | None = Field(
        None,
        description="Total magnetization normalized by volume in μB/Å³.",
    )

    total_magnetization_normalized_formula_units: float | None = Field(
        None,
        description="Total magnetization normalized by formula unit in μB/f.u. .",
    )

    num_magnetic_sites: int | None = Field(
        None,
        description="The number of magnetic sites.",
    )

    num_unique_magnetic_sites: int | None = Field(
        None,
        description="The number of unique magnetic sites.",
    )

    types_of_magnetic_species: list[ElementType] | None = Field(
        None,
        description="Magnetic specie elements.",
    )

    # Elasticity

    # k_voigt: float | None = Field(None, description="Voigt average of the bulk modulus.")

    # k_reuss: float | None = Field(None, description="Reuss average of the bulk modulus in GPa.")

    # k_vrh: float | None = Field(None, description="Voigt-Reuss-Hill average of the bulk modulus in GPa.")

    # g_voigt: float | None = Field(None, description="Voigt average of the shear modulus in GPa.")

    # g_reuss: float | None = Field(None, description="Reuss average of the shear modulus in GPa.")

    # g_vrh: float | None = Field(None, description="Voigt-Reuss-Hill average of the shear modulus in GPa.")

    bulk_modulus: dict[str, float] | None = Field(
        None,
        description="Voigt, Reuss, and Voigt-Reuss-Hill averages of the bulk modulus in GPa.",
    )

    shear_modulus: dict[str, float] | None = Field(
        None,
        description="Voigt, Reuss, and Voigt-Reuss-Hill averages of the shear modulus in GPa.",
    )

    universal_anisotropy: float | None = Field(None, description="Elastic anisotropy.")

    homogeneous_poisson: float | None = Field(None, description="Poisson's ratio.")

    # Dielectric and Piezo

    e_total: float | None = Field(
        None,
        description="Total dielectric constant.",
    )

    e_ionic: float | None = Field(
        None,
        description="Ionic contribution to dielectric constant.",
    )

    e_electronic: float | None = Field(
        None,
        description="Electronic contribution to dielectric constant.",
    )

    n: float | None = Field(
        None,
        description="Refractive index.",
    )

    e_ij_max: float | None = Field(
        None,
        description="Piezoelectric modulus.",
    )

    # Surface Properties

    weighted_surface_energy_EV_PER_ANG2: float | None = Field(
        None,
        description="Weighted surface energy in eV/Å².",
    )

    weighted_surface_energy: float | None = Field(
        None,
        description="Weighted surface energy in J/m².",
    )

    weighted_work_function: float | None = Field(
        None,
        description="Weighted work function in eV.",
    )

    surface_anisotropy: float | None = Field(
        None,
        description="Surface energy anisotropy.",
    )

    shape_factor: float | None = Field(
        None,
        description="Shape factor.",
    )

    has_reconstructed: bool | None = Field(
        None,
        description="Whether the material has any reconstructed surfaces.",
    )

    # Oxi States

    possible_species: list[str] | None = Field(
        None,
        description="Possible charged species in this material.",
    )

    # Has Props

    has_props: dict[str, bool] | None = Field(
        None,
        description="List of properties that are available for a given material.",
    )

    # Theoretical

    theoretical: bool = Field(
        True,
        description="Whether the material is theoretical.",
    )

    # External Database IDs

    database_IDs: dict[str, list[str]] = Field(
        {}, description="External database IDs corresponding to this material."
    )

    @classmethod
    def from_docs(
        cls, material_id: IdentifierType | None = None, **docs: dict[str, dict]
    ) -> Self:
        """Converts a bunch of summary docs into a SummaryDoc"""
        doc = _copy_from_doc(docs)

        # Reshape document for various sub-sections
        # Electronic Structure + Bandstructure + DOS
        if "bandstructure" in doc:
            if doc["bandstructure"] is not None and list(
                filter(lambda x: x is not None, doc["bandstructure"].values())
            ):
                doc["has_props"]["bandstructure"] = True
            else:
                del doc["bandstructure"]
        if "dos" in doc:
            if doc["dos"] is not None and list(
                filter(lambda x: x is not None, doc["dos"].values())
            ):
                doc["has_props"]["dos"] = True
            else:
                del doc["dos"]
        if "task_id" in doc:
            del doc["task_id"]

        return SummaryDoc(material_id=material_id, **doc)


# Key mapping
summary_fields: dict[str, list] = {
    HasProps(k).value: v
    for k, v in {
        "materials": [
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
            "builder_meta",
        ],
        "thermo": [
            "uncorrected_energy_per_atom",
            "energy_per_atom",
            "formation_energy_per_atom",
            "energy_above_hull",
            "is_stable",
            "equilibrium_reaction_energy_per_atom",
            "decomposes_to",
        ],
        "xas": ["absorbing_element", "edge", "spectrum_type", "spectrum_id"],
        "grain_boundaries": [
            "gb_energy",
            "sigma",
            "type",
            "rotation_angle",
            "w_sep",
        ],
        "electronic_structure": [
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
        "magnetism": [
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
        "elasticity": [
            "bulk_modulus",
            "shear_modulus",
            "universal_anisotropy",
            "homogeneous_poisson",
        ],
        "dielectric": ["e_total", "e_ionic", "e_electronic", "n"],
        "piezoelectric": ["e_ij_max"],
        "surface_properties": [
            "weighted_surface_energy",
            "weighted_surface_energy_EV_PER_ANG2",
            "shape_factor",
            "surface_anisotropy",
            "weighted_work_function",
            "has_reconstructed",
        ],
        "oxi_states": ["possible_species"],
        "provenance": ["theoretical", "database_IDs"],
        "charge_density": [],
        "eos": [],
        "phonon": [],
        "absorption": [],
        "insertion_electrodes": [],
        "substrates": [],
        "chemenv": [],
    }.items()
}


def _copy_from_doc(doc):
    """Helper function to copy the list of keys over from amalgamated document"""
    has_props = {str(val.value): False for val in HasProps}
    d = {"has_props": has_props, "origins": []}
    # Complex function to grab the keys and put them in the root doc
    # if the item is a list, it makes one doc per item with those corresponding keys
    for doc_key in summary_fields:
        sub_doc = doc.get(doc_key, None)
        if isinstance(sub_doc, list) and len(sub_doc) > 0:
            d["has_props"][doc_key] = True
            d[doc_key] = []
            for sub_item in sub_doc:
                temp_doc = {
                    copy_key: sub_item[copy_key]
                    for copy_key in summary_fields[doc_key]
                    if copy_key in sub_item
                }
                d[doc_key].append(temp_doc)
        elif isinstance(sub_doc, dict):
            d["has_props"][doc_key] = True
            if sub_doc.get("origins", None):
                d["origins"].extend(sub_doc["origins"])
            d.update(
                {
                    copy_key: sub_doc[copy_key]
                    for copy_key in summary_fields[doc_key]
                    if copy_key in sub_doc
                }
            )
    return d
