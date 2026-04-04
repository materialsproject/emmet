from __future__ import annotations

from collections import ChainMap
from itertools import chain
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, PrivateAttr

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
    Enum of possible has_props values.
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
    absorption = "absorption"
    insertion_electrodes = "insertion_electrodes"
    substrates = "substrates"
    chemenv = "chemenv"


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


class PropModel(BaseModel):
    """Check for model initialization outside of defaults."""

    _prop: str = PrivateAttr("material")

    @property
    def _has_props(self) -> bool:
        return not not self.model_fields_set

    @property
    def name(self) -> HasProps:
        return HasProps[self._prop]


class MaterialsSummary(PropertyDoc, PropModel):
    task_ids: list[IdentifierType] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs associated with this material.",
    )
    structure: StructureType = Field(
        ..., description="The lowest energy structure for this material."
    )


class ThermoSummary(PropModel):
    _prop: str = PrivateAttr("thermo")
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


class XASSearchData(PropModel):
    """
    Fields in XAS sub docs in summary
    """

    edge: XasEdge | None = Field(
        None, title="Absorption Edge", description="The interaction edge for XAS"
    )
    absorbing_element: ElementType | None = Field(
        None, description="Absorbing element."
    )
    spectrum_type: XasType | None = Field(None, description="Type of XAS spectrum.")


class XASSummary(PropModel):
    _prop: str = PrivateAttr("xas")
    xas: list[XASSearchData] | None = Field(
        None,
        description="List of xas documents.",
    )


class GBSearchData(BaseModel):
    """
    Fields in grain boundary sub docs in summary
    """

    sigma: int | None = Field(None, description="Sigma value of the boundary.")
    type: str | None = Field(None, description="Grain boundary type.")
    gb_energy: float | None = Field(None, description="Grain boundary energy in J/m^2.")
    rotation_angle: float | None = Field(None, description="Rotation angle in degrees.")


class GBSummary(BaseModel):
    _prop: str = PrivateAttr("grain_boundaries")
    grain_boundaries: list[GBSearchData] | None = Field(
        None, description="List of grain boundary documents."
    )


class ElectronicStructureSummary(PropModel):
    _prop: str = PrivateAttr("electronic_structure")
    band_gap: float | None = Field(None, description="Band gap energy in eV.")
    cbm: float | None = Field(None, description="Conduction band minimum data.")
    vbm: float | None = Field(None, description="Valence band maximum data.")
    efermi: float | None = Field(None, description="Fermi energy in eV.")
    is_gap_direct: bool | None = Field(
        None, description="Whether the band gap is direct."
    )
    is_metal: bool | None = Field(None, description="Whether the material is a metal.")


class BandstructureSummary(PropModel):
    _prop: str = PrivateAttr("bandstructure")
    bandstructure: BandstructureData | None = Field(
        None, description="Band structure data for the material."
    )


class DosSummary(PropModel):
    _prop: str = PrivateAttr("dos")
    dos: DosData | None = Field(
        None, description="Density of states data for the material."
    )
    dos_energy_up: float | None = Field(None, description="Spin-up DOS band gap in eV.")
    dos_energy_down: float | None = Field(
        None, description="Spin-down DOS band gap in eV."
    )


class MagnetismSummary(PropModel):
    _prop: str = PrivateAttr("magnetism")
    is_magnetic: bool | None = Field(
        None, description="Whether the material is magnetic."
    )
    ordering: str | None = Field(None, description="Type of magnetic ordering.")
    total_magnetization: float | None = Field(
        None, description="Total magnetization in μB."
    )
    total_magnetization_normalized_vol: float | None = Field(
        None, description="Total magnetization normalized by volume in μB/Å³."
    )
    total_magnetization_normalized_formula_units: float | None = Field(
        None, description="Total magnetization normalized by formula unit in μB/f.u. ."
    )
    num_magnetic_sites: int | None = Field(
        None, description="The number of magnetic sites."
    )
    num_unique_magnetic_sites: int | None = Field(
        None, description="The number of unique magnetic sites."
    )
    types_of_magnetic_species: list[ElementType] | None = Field(
        None, description="Magnetic species elements."
    )


class ElasticitySummary(PropModel):
    _prop: str = PrivateAttr("elasticity")
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


class DielectricSummary(PropModel):
    _prop: str = PrivateAttr("dielectric")
    e_total: float | None = Field(None, description="Total dielectric constant.")
    e_ionic: float | None = Field(
        None, description="Ionic contribution to dielectric constant."
    )
    e_electronic: float | None = Field(
        None, description="Electronic contribution to dielectric constant."
    )
    n: float | None = Field(None, description="Refractive index.")


class PiezoelectricSummary(PropModel):
    _prop: str = PrivateAttr("piezoelectric")
    e_ij_max: float | None = Field(None, description="Piezoelectric modulus.")


class SurfacesSummary(PropModel):
    _prop: str = PrivateAttr("surfaces")
    weighted_surface_energy_EV_PER_ANG2: float | None = Field(
        None, description="Weighted surface energy in eV/Å²."
    )
    weighted_surface_energy: float | None = Field(
        None, description="Weighted surface energy in J/m²."
    )
    weighted_work_function: float | None = Field(
        None, description="Weighted work function in eV."
    )
    surface_anisotropy: float | None = Field(
        None, description="Surface energy anisotropy."
    )
    shape_factor: float | None = Field(None, description="Shape factor.")
    has_reconstructed: bool | None = Field(
        None, description="Whether the material has any reconstructed surfaces."
    )


class OxiStatesSummary(PropModel):
    _prop: str = PrivateAttr("oxi_states")
    possible_species: list[str] | None = Field(
        None, description="Possible charged species in this material."
    )


class ProvenanceSummary(PropModel):
    _prop: str = PrivateAttr("provenance")
    theoretical: bool = Field(True, description="Whether the material is theoretical.")
    database_IDs: dict[str, list[str]] | None = Field(
        None, description="External database IDs corresponding to this material."
    )


# -----------------------------------------------------------------------------
# Shims for populating has_props for properties that do not add
# values to SummaryDoc
# -----------------------------------------------------------------------------
class ChargeDensityData(PropModel):
    _prop: str = PrivateAttr("charge_density")
    exists: bool = False


class EosData(PropModel):
    _prop: str = PrivateAttr("eos")
    exists: bool = False


class PhononData(PropModel):
    _prop: str = PrivateAttr("phonon")
    exists: bool = False


class AbsorptionData(PropModel):
    _prop: str = PrivateAttr("absorption")
    exists: bool = False


class ElectrodesData(PropModel):
    _prop: str = PrivateAttr("insertion_electrodes")
    exists: bool = False


class SubstratesData(PropModel):
    _prop: str = PrivateAttr("substrates")
    exists: bool = False


class ChemenvData(PropModel):
    _prop: str = PrivateAttr("chemenv")
    exists: bool = False


class SummaryDoc(
    MaterialsSummary,
    ThermoSummary,
    XASSummary,
    GBSummary,
    ElectronicStructureSummary,
    BandstructureSummary,
    DosSummary,
    MagnetismSummary,
    ElasticitySummary,
    DielectricSummary,
    PiezoelectricSummary,
    SurfacesSummary,
    OxiStatesSummary,
    ProvenanceSummary,
):
    """
    Summary information about materials and their properties, useful for materials
    screening studies and searching.
    """

    has_props: dict[HasProps, bool] | None = Field(
        None,
        description="List of properties that are available for a given material.",
    )

    @classmethod
    def from_docs(
        cls,
        property_summary_docs: list[
            MaterialsSummary
            | ThermoSummary
            | XASSummary
            | GBSummary
            | ElectronicStructureSummary
            | BandstructureSummary
            | DosSummary
            | MagnetismSummary
            | ElasticitySummary
            | DielectricSummary
            | PiezoelectricSummary
            | SurfacesSummary
            | OxiStatesSummary
            | ProvenanceSummary
        ],
        property_shim_docs: list[
            ChargeDensityData
            | EosData
            | PhononData
            | AbsorptionData
            | ElectrodesData
            | SubstratesData
            | ChemenvData
        ],
        **kwargs,
    ) -> Self:
        """
        Args:
            property_summary_docs: List of propery documents with data to
                be added to SummaryDoc.
            property_shim_docs: List of property shim documents strictly
                used to populate has_props.
        """
        # initialize all has_props variants to False, overwrite according to what caller provides
        has_props = {prop.value: False for prop in HasProps}
        for prop in chain(property_summary_docs, property_summary_docs):
            has_props[prop.name] = prop._has_props

        return SummaryDoc(
            has_props=has_props,
            **ChainMap(*[doc.model_dump() for doc in property_summary_docs]),
            **kwargs,
        )
