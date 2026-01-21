from pymatgen.analysis.local_env import CrystalNN
import pytest

from emmet.core.featurization.robocrys.condense.site import (
    SiteAnalyzer,
    geometries_match,
    nn_summaries_match,
    nnn_summaries_match,
)


@pytest.fixture
def cnn():
    return CrystalNN()


@pytest.fixture
def tin_dioxide(cnn, test_structures):
    return cnn.get_bonded_structure(test_structures["SnO2"].copy())


@pytest.fixture
def ba_n(cnn, test_structures):
    return cnn.get_bonded_structure(test_structures["BaN2"].copy())


def test_init(tin_dioxide, ba_n):
    """Test to check SiteDescriber can be initialised."""
    sa = SiteAnalyzer(tin_dioxide)
    assert sa is not None, "tin dioxide site analyzer could not be init"

    # check different structure
    sa = SiteAnalyzer(ba_n)
    assert sa is not None, "BaN2 site analyzer could not be initialized"


def test_equivalent_sites(ba_n):
    """Check equivalent sites instance variable set correctly."""
    sa = SiteAnalyzer(ba_n, use_symmetry_equivalent_sites=False)
    assert sa.equivalent_sites == [0, 0, 0, 0, 4, 4]

    # test using symmetry to determine equivalent sites
    sa = SiteAnalyzer(ba_n, use_symmetry_equivalent_sites=True)
    assert isinstance(sa.equivalent_sites, list)
    assert sa.equivalent_sites == [0, 0, 0, 0, 4, 4]

    # test symprec option works
    sa = SiteAnalyzer(ba_n, use_symmetry_equivalent_sites=True, symprec=0.0001)
    assert sa.equivalent_sites == [0, 1, 1, 0, 4, 4]


def test_symmetry_labels(ba_n):
    """Check equivalent sites instance variable set correctly."""
    sa = SiteAnalyzer(ba_n, use_symmetry_equivalent_sites=False)
    assert sa.symmetry_labels == [1, 1, 1, 1, 1, 1]


def test_get_site_geometry(tin_dioxide, ba_n):
    """Test site geometry description."""
    sa = SiteAnalyzer(tin_dioxide)
    geom_data = sa.get_site_geometry(0)
    assert geom_data["type"] == "octahedral"
    assert geom_data["likeness"] == pytest.approx(0.9349776258427136)

    geom_data = sa.get_site_geometry(4)
    assert geom_data["type"] == "trigonal planar"
    assert geom_data["likeness"] == pytest.approx(0.6050243049545359)

    # check different structure

    sa = SiteAnalyzer(ba_n)
    geom_data = sa.get_site_geometry(0)
    assert geom_data["type"] == "6-coordinate"
    assert geom_data["likeness"] == 1


def test_get_nearest_neighbors(tin_dioxide, ba_n):
    """Check getting nearest neighbors."""
    sa = SiteAnalyzer(tin_dioxide)
    info = sa.get_nearest_neighbors(4)

    assert len(info) == 3
    assert info[0]["element"] == "Sn4+"
    assert info[0]["inequiv_index"] == 0
    assert info[0]["dist"] == pytest.approx(2.0922101061490546)

    info = sa.get_nearest_neighbors(0, inc_inequivalent_site_index=False)
    assert "inequiv_index" not in info[0]

    # check different structure without oxi state
    sa = SiteAnalyzer(ba_n)
    info = sa.get_nearest_neighbors(0)
    assert len(info) == 6
    assert info[0]["element"] == "N"
    assert info[0]["inequiv_index"] == 0
    assert info[0]["dist"] == pytest.approx(1.2619877178483)


def test_get_next_nearest_neighbors(tin_dioxide, ba_n):
    """Check getting next nearest neighbors."""
    sa = SiteAnalyzer(tin_dioxide)
    info = sa.get_next_nearest_neighbors(5)

    assert len(info) == 14
    idx = [i for i, s in enumerate(info) if s["connectivity"] == "edge"][0]
    assert info[idx]["element"] == "O2-"
    assert info[idx]["connectivity"] == "edge"
    assert info[idx]["geometry"]["type"] == "trigonal planar"
    assert info[idx]["inequiv_index"] == 2

    info = sa.get_next_nearest_neighbors(0, inc_inequivalent_site_index=False)
    assert "inequiv_index" not in info[0]

    info = sa.get_next_nearest_neighbors(0)
    assert info[0]["element"] == "Sn4+"
    assert info[0]["connectivity"] == "edge"
    assert info[0]["geometry"]["type"] == "octahedral"
    assert len(info[0]["angles"]) == 2
    assert info[0]["angles"][0] == pytest.approx(101.62287790513848)
    assert info[0]["distance"] == pytest.approx(3.24322132)

    # check different structure without oxi state
    sa = SiteAnalyzer(ba_n)
    info = sa.get_next_nearest_neighbors(0)
    assert len(info) == 36
    assert info[5]["element"] == "N"
    assert info[5]["connectivity"] == "edge"
    assert info[5]["geometry"]["type"] == "6-coordinate"
    assert len(info[5]["angles"]) == 2
    assert info[5]["angles"][0] == pytest.approx(83.91397867959587)
    assert info[5]["distance"] == pytest.approx(3.549136232944574)


def test_get_site_summary(tin_dioxide):
    """Test getting the site summary."""
    sa = SiteAnalyzer(tin_dioxide)
    data = sa.get_site_summary(0)
    assert data["element"] == "Sn4+"
    assert data["geometry"]["type"] == "octahedral"
    assert data["geometry"]["likeness"] == pytest.approx(0.9349776258427136)
    assert len(data["nn"]) == 6
    assert len(data["nnn"]["corner"]) == 8
    assert len(data["nnn"]["edge"]) == 2
    assert data["poly_formula"] == "O6"
    assert data["sym_labels"] == (1,)


def test_get_bond_distance_summary(tin_dioxide):
    """Test getting the bond distance summary."""
    sa = SiteAnalyzer(tin_dioxide)
    data = sa.get_bond_distance_summary(0)

    assert len(data[2]) == 6
    assert data[2][0] == pytest.approx(2.0922101061490546)


def test_connectivity_angle_summary(tin_dioxide):
    """Test getting the connectivity angle summary."""
    sa = SiteAnalyzer(tin_dioxide)
    data = sa.get_connectivity_angle_summary(0)

    assert len(data[0]["corner"]) == 8
    assert len(data[0]["edge"]) == 4
    assert data[0]["edge"][0] == pytest.approx(101.62287790513848)


def test_nnn_distance_summary(tin_dioxide):
    """Test getting the nnn distance summary."""
    sa = SiteAnalyzer(tin_dioxide)
    data = sa.get_nnn_distance_summary(0)

    assert len(data[0]["corner"]) == 8
    assert len(data[0]["edge"]) == 2
    assert data[0]["edge"][0] == pytest.approx(3.24322132)


def test_get_all_site_summaries(tin_dioxide):
    """Test getting all the site summaries."""
    sa = SiteAnalyzer(tin_dioxide)
    data = sa.get_all_site_summaries()
    assert len(data.keys()) == 2
    assert data[0]["element"] == "Sn4+"
    assert data[0]["geometry"]["type"] == "octahedral"
    assert data[0]["geometry"]["likeness"] == pytest.approx(0.9349776258427136)
    assert len(data[0]["nn"]) == 6
    assert len(data[0]["nnn"]["corner"]) == 8
    assert len(data[0]["nnn"]["edge"]) == 2
    assert data[0]["poly_formula"] == "O6"
    assert data[0]["sym_labels"] == (1,)


def test_get_all_bond_distance_summaries(tin_dioxide):
    sa = SiteAnalyzer(tin_dioxide)
    data = sa.get_all_bond_distance_summaries()
    assert len(data[0][2]) == 6
    assert len(data[2][0]) == 3
    assert data[0][2][0] == pytest.approx(2.0922101061490546)


def test_get_all_connectivity_angle_summaries(tin_dioxide):
    sa = SiteAnalyzer(tin_dioxide)
    data = sa.get_all_connectivity_angle_summaries()
    assert len(data[0][0]["corner"]) == 8
    assert len(data[0][0]["edge"]) == 4
    assert data[0][0]["edge"][0] == pytest.approx(101.62287790513848)


def test_get_all_nnn_distance_summaries(tin_dioxide):
    sa = SiteAnalyzer(tin_dioxide)
    data = sa.get_all_nnn_distance_summaries()
    assert len(data[0][0]["corner"]) == 8
    assert len(data[0][0]["edge"]) == 2
    assert data[0][0]["edge"][0] == pytest.approx(3.24322132)


def test_get_inequivalent_site_indices(ba_n):
    sa = SiteAnalyzer(ba_n, use_symmetry_equivalent_sites=False)
    inequiv_indices = sa.get_inequivalent_site_indices(list(range(6)))
    assert inequiv_indices == [0, 0, 0, 0, 4, 4]

    # test using symmetry to determine inequivalent sites.
    sa = SiteAnalyzer(ba_n, use_symmetry_equivalent_sites=True)
    inequiv_indices = sa.get_inequivalent_site_indices(list(range(6)))
    assert inequiv_indices == [0, 0, 0, 0, 4, 4]

    # test symprec option
    sa = SiteAnalyzer(ba_n, use_symmetry_equivalent_sites=True, symprec=0.000001)
    inequiv_indices = sa.get_inequivalent_site_indices(list(range(6)))
    assert inequiv_indices == [0, 1, 1, 0, 4, 4]


def test_geometries_match(tin_dioxide):
    """Test geometry matching function."""
    sa = SiteAnalyzer(tin_dioxide, use_symmetry_equivalent_sites=False)
    geom_a = sa.get_site_geometry(0)
    geom_b = sa.get_site_geometry(1)
    geom_c = sa.get_site_geometry(4)

    assert geometries_match(geom_a, geom_b)
    assert not geometries_match(geom_a, geom_c)


def test_nn_summaries_match(ba_n):
    """Test nearest neighbour summary matching function."""
    sa = SiteAnalyzer(ba_n, use_symmetry_equivalent_sites=True)
    nn_a = sa.get_nearest_neighbors(0)
    nn_b = sa.get_nearest_neighbors(1)
    nn_c = sa.get_nearest_neighbors(4)

    assert nn_summaries_match(nn_a, nn_b)
    assert not nn_summaries_match(nn_a, nn_c)

    # test bond dist tol works
    assert not nn_summaries_match(nn_a, nn_b, bond_dist_tol=1e-10)

    # test not matching bond dists
    assert nn_summaries_match(nn_a, nn_b, bond_dist_tol=1e-10, match_bond_dists=False)


def test_nnn_summaries_match(ba_n):
    """Test nearest neighbour summary matching function."""
    sa = SiteAnalyzer(ba_n, use_symmetry_equivalent_sites=True)
    nnn_a = sa.get_next_nearest_neighbors(0)
    nnn_b = sa.get_next_nearest_neighbors(3)
    nnn_c = sa.get_next_nearest_neighbors(4)

    assert nnn_summaries_match(nnn_a, nnn_b)
    assert not nnn_summaries_match(nnn_a, nnn_c)

    # test not matching bond angles
    assert nnn_summaries_match(
        nnn_a, nnn_b, bond_angle_tol=1e-10, match_bond_angles=False
    )
