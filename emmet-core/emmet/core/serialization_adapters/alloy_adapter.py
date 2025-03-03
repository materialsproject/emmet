import pymatgen.analysis.alloys.core
from pydantic import RootModel
from pymatgen.core import Composition, Structure
from typing_extensions import TypedDict


class TypedSupportedPropertiesDict(TypedDict):
    energy_above_hull: float
    formation_energy_per_atom: float
    band_gap: float
    is_gap_direct: bool
    m_n: float
    m_p: float
    theoretical: bool
    is_metal: bool


class TypedAlloyMemberDict(TypedDict):
    id_: str
    db: str
    composition: Composition
    x: float
    is_ordered: bool


TypedAlloyPairDict = TypedDict(
    "TypedAlloyPairDict",
    {
        "@module": str,
        "@class": str,
        "@version": str,
        "formula_a": str,
        "formula_b": str,
        "structure_a": Structure,
        "structure_b": Structure,
        "id_a": str,
        "id_b": str,
        "chemsys": str,
        "alloying_element_a": str,
        "alloying_element_b": str,
        "alloying_species_a": list[str],
        "alloying_species_b": list[str],
        "observer_elements": list[str],
        "observer_species": list[str],
        "anions_a": list[str],
        "anions_b": list[str],
        "cations_a": list[str],
        "cations_b": list[str],
        "lattice_parameters_a": list[float],
        "lattice_parameters_b": list[float],
        "volume_cube_root_a": float,
        "volume_cube_root_b": float,
        "properties_a": TypedSupportedPropertiesDict,
        "properties_b": TypedSupportedPropertiesDict,
        "spacegroup_intl_number_a": int,
        "spacegroup_intl_number_b": int,
        "pair_id": str,
        "pair_formula": str,
        "alloy_oxidation_state": int,
        "isoelectronic": bool,
        "anonymous_formula": str,
        "nelements": int,
        "members": list[TypedAlloyMemberDict],
    },
)

TypedAlloySystemDict = TypedDict(
    "TypedAlloySystemDict",
    {
        "@class": str,
        "@module": str,
        "@version": str,
        "alloy_id": str,
        "alloy_pairs": list[TypedAlloyPairDict],
        "chemsys": str,
        "chemsys_size": int,
        "has_members": bool,
        "members": list[TypedAlloyMemberDict],
        "additional_members": list[TypedAlloyMemberDict],
        "n_pairs": int,
        "ids": list[str],
        "pair_ids": list[str],
    },
)


class AlloyMemberAdapter(RootModel):
    root: TypedAlloyMemberDict


class AlloyPairAdapter(RootModel):
    root: TypedAlloyPairDict


class AlloySystemAdapter(RootModel):
    root: TypedAlloySystemDict


pymatgen.analysis.alloys.core.AlloyMember.__pydantic_model__ = AlloyMemberAdapter
pymatgen.analysis.alloys.core.AlloyPair.__pydantic_model__ = AlloyPairAdapter
pymatgen.analysis.alloys.core.AlloySystem.__pydantic_model__ = AlloySystemAdapter
