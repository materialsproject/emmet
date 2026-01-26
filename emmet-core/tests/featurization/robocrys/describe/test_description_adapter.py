import pytest

from emmet.core.featurization.robocrys.describe.adapter import DescriptionAdapter


@pytest.fixture
def tin_dioxide_da(test_condensed_structures):
    return DescriptionAdapter(test_condensed_structures["SnO2"].copy())


@pytest.fixture
def mapi_da(test_condensed_structures):
    return DescriptionAdapter(test_condensed_structures["mapi"].copy())


def test_attributes(mapi_da):
    assert mapi_da.mineral["type"] == "Orthorhombic Perovskite"
    assert mapi_da.mineral["distance"] == -1
    assert mapi_da.formula == "CH3NH3PbI3"
    assert mapi_da.spg_symbol == "Pnma"
    assert mapi_da.crystal_system == "orthorhombic"
    assert mapi_da.dimensionality == 3
    assert mapi_da.sites
    assert mapi_da.distances
    assert mapi_da.angles
    assert mapi_da.components
    assert mapi_da.component_makeup
    assert mapi_da.elements[0] == "H+"
    assert mapi_da.sym_labels[0] == "(1)"


def test_get_nearest_neighbor_details(tin_dioxide_da, mapi_da):
    """Check getting nearest neighbor summary for all neighbors."""
    all_details = tin_dioxide_da.get_nearest_neighbor_details(0)

    assert len(all_details) == 1
    details = all_details[0]
    assert details.element == "O2-"
    assert details.count == 6
    assert details.sites == [2]
    assert details.sym_label == "(1)"

    # test merging of sym labels
    all_details = mapi_da.get_nearest_neighbor_details(24, group=True)
    details = all_details[0]
    assert details.element == "I-"
    assert details.count == 6
    assert details.sites == [32, 36]
    assert details.sym_label == "(1,2)"


def test_get_next_nearest_neighbor_details(tin_dioxide_da):
    all_details = tin_dioxide_da.get_next_nearest_neighbor_details(0)

    assert len(all_details) == 2
    details = all_details[0]
    assert details.element == "Sn4+"
    assert details.count == 8
    assert details.sites == [0]
    assert details.geometry == "octahedral"
    assert details.connectivity == "corner"
    assert details.poly_formula == "O6"
    assert details.sym_label == "(1)"


def test_get_distance_details(tin_dioxide_da, mapi_da):
    # test get distance using int works
    distances = tin_dioxide_da.get_distance_details(0, 2)
    assert len(distances), 3
    assert distances[0] == pytest.approx(2.0922101061490546)

    # test get distance using list works
    distances = tin_dioxide_da.get_distance_details(0, [2])
    assert len(distances), 3
    assert distances[0] == pytest.approx(2.0922101061490546)

    # test getting multiple distances
    distances = mapi_da.get_distance_details(44, [0, 8])
    assert len(distances), 4
    assert distances[0] == pytest.approx(1.0386222568611572)


def test_get_angle_details(tin_dioxide_da):
    # test get angles using int works
    distances = tin_dioxide_da.get_angle_details(0, 0, "corner")
    assert len(distances), 8
    assert distances[0] == pytest.approx(129.18849530149342)

    # test get angles using list works
    distances = tin_dioxide_da.get_angle_details(0, [0], "corner")
    assert len(distances), 8
    assert distances[0] == pytest.approx(129.18849530149342)


def test_get_component_details(mapi_da):
    """Check getting component details."""
    all_details = mapi_da.get_component_details()
    assert len(all_details) == 2

    details = all_details[0]
    assert details.formula == "CH3NH3"
    assert details.count == 4
    assert details.dimensionality == 0
    assert details.molecule_name == "methylammonium"
    assert details.orientation is None
    assert details.index == 0


def test_get_component_summary(mapi_da):
    """Check getting the component summaries."""
    all_groups = mapi_da.get_component_groups()
    assert len(all_groups) == 2

    group = all_groups[0]
    assert group.count == 4
    assert group.formula == "CH3NH3"
    assert group.dimensionality == 0
    assert group.molecule_name == "methylammonium"

    details = group.components[0]
    assert details.formula == "CH3NH3"
    assert details.count == 4
    assert details.dimensionality == 0
    assert details.molecule_name == "methylammonium"
    assert details.orientation is None
    assert details.index == 0


def test_component_site_groups(mapi_da):
    """Check getting the SiteGroups in a component."""
    all_groups = mapi_da.get_component_site_groups(1)
    assert len(all_groups) == 2
    group = all_groups[1]
    assert group.element == "I-"
    assert group.count == 2
    assert group.sites == [32, 36]


def test_get_sym_label(mapi_da):
    """Test getting symmetry labels."""
    assert mapi_da.get_sym_label(0) == "(1)"

    # test using list to get sym label
    assert mapi_da.get_sym_label([0]) == "(1)"

    # test combining multiple labels
    assert mapi_da.get_sym_label([0, 24]) == "(1,1)"
