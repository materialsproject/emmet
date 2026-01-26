from pymatgen.analysis.dimensionality import get_structure_components
from pymatgen.analysis.local_env import CrystalNN
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
import pytest

from emmet.core.featurization.robocrys.condense.component import (
    components_are_isomorphic,
    components_are_vdw_heterostructure,
    filter_molecular_components,
    get_component_formula,
    get_component_formula_and_factor,
    get_formula_from_components,
    get_formula_inequiv_components,
    get_reconstructed_structure,
    get_structure_inequiv_components,
    get_sym_inequiv_components,
    get_vdw_heterostructure_information,
)


@pytest.fixture
def mapi(test_structures):
    return CrystalNN().get_bonded_structure(test_structures["mapi"].copy())


@pytest.fixture
def mapi_components(mapi):
    return get_structure_components(
        mapi, inc_molecule_graph=True, inc_site_ids=True, inc_orientation=True
    )


@pytest.fixture
def vdw_hetero(test_structures):
    return CrystalNN().get_bonded_structure(test_structures["MoWS4"])


@pytest.fixture
def vdw_hetero_components(vdw_hetero):
    return get_structure_components(
        vdw_hetero,
        inc_molecule_graph=True,
        inc_site_ids=True,
        inc_orientation=True,
    )


def test_get_component_formula_and_factor(mapi_components):
    """Test getting the component formula and factor."""
    formula, factor = get_component_formula_and_factor(
        mapi_components[0], use_common_formulas=True, use_iupac_formula=True
    )
    assert formula == "CH3NH3"
    assert factor == 1

    formula, factor = get_component_formula_and_factor(
        mapi_components[4], use_common_formulas=True, use_iupac_formula=True
    )
    assert formula == "PbI3"
    assert factor == 4

    # test without common formulas
    formula, factor = get_component_formula_and_factor(
        mapi_components[0], use_common_formulas=False, use_iupac_formula=True
    )
    assert formula == "CNH6"
    assert factor == 1

    # test without common formulas and without iupac formula
    formula, factor = get_component_formula_and_factor(
        mapi_components[0], use_common_formulas=False, use_iupac_formula=False
    )
    assert formula == "H6CN"
    assert factor == 1


def test_get_component_formula(mapi_components):
    """Test getting the component formula."""
    formula = get_component_formula(
        mapi_components[0], use_common_formulas=True, use_iupac_formula=True
    )
    assert formula == "CH3NH3"

    formula = get_component_formula(
        mapi_components[4], use_common_formulas=True, use_iupac_formula=True
    )
    assert formula == "PbI3"

    # test without common formulas
    formula = get_component_formula(
        mapi_components[0], use_common_formulas=False, use_iupac_formula=True
    )
    assert formula == "CNH6"

    # test without common formulas and without iupac formula
    formula = get_component_formula(
        mapi_components[0], use_common_formulas=False, use_iupac_formula=False
    )
    assert formula == "H6CN"


def test_get_sym_inequiv_components(mapi, mapi_components):
    """Test getting symmetrically inequivalent structure components."""
    sga = SpacegroupAnalyzer(mapi.structure, symprec=0.01)

    inequiv_comp = get_sym_inequiv_components(mapi_components, sga)

    assert len(inequiv_comp) == 2
    assert inequiv_comp[0]["count"] == 4
    assert inequiv_comp[1]["count"] == 1


def test_get_comp_inequiv_components(mapi_components):
    """Test getting compositionally inequivalent structure components."""
    inequiv_comp = get_formula_inequiv_components(mapi_components)

    assert len(inequiv_comp) == 2
    assert inequiv_comp[0]["count"] == 4
    assert inequiv_comp[0]["formula"] == "CH3NH3"
    assert inequiv_comp[1]["count"] == 4
    assert inequiv_comp[1]["formula"] == "PbI3"

    # Test not using common_formulas but with iupac formula
    inequiv_comp = get_formula_inequiv_components(
        mapi_components, use_iupac_formula=True, use_common_formulas=False
    )
    assert inequiv_comp[0]["count"] == 4
    assert inequiv_comp[0]["formula"] == "CNH6"

    # test non-iupac formula
    inequiv_comp = get_formula_inequiv_components(
        mapi_components, use_iupac_formula=False, use_common_formulas=False
    )
    assert inequiv_comp[0]["count"] == 4
    assert inequiv_comp[0]["formula"] == "H6CN"


def test_filter_molecular_components(mapi_components):
    """Test filtering of molecular components."""
    mol_comps, comps = filter_molecular_components(mapi_components)
    mol_dimen = list({c["dimensionality"] for c in mol_comps})
    other_dimen = list({c["dimensionality"] for c in comps})

    assert len(mol_comps) == 4
    assert len(mol_dimen) == 1
    assert mol_dimen[0] == 0

    assert len(comps) == 1
    assert 0 not in other_dimen


def test_get_reconstructed_structure(mapi, mapi_components):
    structure = get_reconstructed_structure(mapi_components, simplify_molecules=False)

    # check the reconstructred structure matches the original using
    # pymatgen's structure matcher.
    sm = StructureMatcher(
        scale=False, primitive_cell=False, ltol=1e-4, stol=1e-4, angle_tol=1e-4
    )
    assert sm.fit(structure, mapi.structure)

    # Test the structure matches when we simplify molecules.
    # To do this we ignore all C, H, and N atoms.
    structure = get_reconstructed_structure(mapi_components, simplify_molecules=True)

    sm = StructureMatcher(
        scale=False,
        primitive_cell=False,
        ltol=1e-4,
        stol=1e-4,
        angle_tol=1e-4,
        ignored_species=["C", "H", "N"],
    )
    assert sm.fit(structure, mapi.structure)


def test_get_formula_from_components(test_structures, mapi_components):
    assert (
        get_formula_from_components(
            mapi_components, use_common_formulas=True, use_iupac_formula=True
        )
        == "CH3NH3PbI3"
    )

    # check not using common formulas
    assert (
        get_formula_from_components(
            mapi_components, use_common_formulas=False, use_iupac_formula=True
        )
        == "CNH6PbI3"
    )

    # check non-iupac ordering works
    assert (
        get_formula_from_components(
            mapi_components, use_iupac_formula=False, use_common_formulas=False
        )
        == "H6CNPbI3"
    )

    # test multiple groups of different numbers of compositions
    s = CrystalNN().get_bonded_structure(test_structures["CuH8CN5Cl3"])
    comps = get_structure_components(s)
    assert (
        get_formula_from_components(
            comps, use_iupac_formula=True, use_common_formulas=True
        )
        == "(CuCN4HCl)2(NH2)2(H2)3(HCl)4"
    )

    # test putting molecules first
    s = CrystalNN().get_bonded_structure(test_structures["ZrCuH8C2NCl6"])
    comps = get_structure_components(s)
    assert (
        get_formula_from_components(
            comps,
            molecules_first=False,
            use_iupac_formula=True,
            use_common_formulas=True,
        )
        == "ZrCuCl6(CH3)2NH2"
    )

    assert (
        get_formula_from_components(
            comps,
            molecules_first=True,
            use_iupac_formula=True,
            use_common_formulas=True,
        )
        == "(CH3)2NH2ZrCuCl6"
    )


def test_components_are_vdw_heterostructure(mapi_components, vdw_hetero_components):
    assert components_are_vdw_heterostructure(vdw_hetero_components)
    assert not components_are_vdw_heterostructure(mapi_components)


def test_get_vdw_heterostructure_information(
    mapi_components, vdw_hetero, vdw_hetero_components
):
    data = get_vdw_heterostructure_information(
        vdw_hetero_components,
        inc_ordered_components=True,
        inc_intercalants=True,
    )
    assert len(data["ordered_components"]) == 4
    assert data["ordered_components"][0]["structure_graph"].structure.frac_coords[0][
        0
    ] == pytest.approx(0.33330876)
    assert data["ordered_components"][3]["structure_graph"].structure.frac_coords[0][
        0
    ] == pytest.approx(0.6666924)
    assert data["repeating_unit"] == ["MoS2", "WS2"]
    assert data["num_repetitions"] == 2
    assert data["intercalants"] == []

    # test error catching
    with pytest.raises(ValueError):
        get_vdw_heterostructure_information(mapi_components)

    with pytest.raises(KeyError):
        get_vdw_heterostructure_information(get_structure_components(vdw_hetero))


def test_components_are_isomorphic(mapi_components):
    # check two CH3NH3 components are isomorphic
    assert components_are_isomorphic(mapi_components[0], mapi_components[1])

    # check CH3NH3 and PbI3 are not isomorphic
    assert not components_are_isomorphic(mapi_components[0], mapi_components[4])


def test_get_structure_inequiv_components(mapi_components):
    inequiv_comp = get_structure_inequiv_components(
        mapi_components, use_structure_graph=False
    )

    assert len(inequiv_comp) == 2
    assert inequiv_comp[0]["count"] == 4

    assert inequiv_comp[1]["count"] == 1

    # test using graph/fingerprint matching
    inequiv_comp = get_structure_inequiv_components(
        mapi_components, use_structure_graph=True
    )

    assert len(inequiv_comp) == 2
    assert inequiv_comp[0]["count"] == 4

    assert inequiv_comp[1]["count"] == 1
