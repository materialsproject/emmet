from __future__ import annotations

import pytest

from emmet.core.featurization.robocrys.adapter import BaseAdapter


@pytest.fixture
def tin_dioxide_ba(test_condensed_structures):
    return BaseAdapter(test_condensed_structures["SnO2"].copy())


@pytest.fixture
def mapi_ba(test_condensed_structures):
    return BaseAdapter(test_condensed_structures["mapi"])


def test_attributes(mapi_ba):
    assert mapi_ba.mineral["type"] == "Orthorhombic Perovskite"
    assert mapi_ba.mineral["distance"] == -1
    assert mapi_ba.formula == "CH3NH3PbI3"
    assert mapi_ba.spg_symbol == "Pnma"
    assert mapi_ba.crystal_system == "orthorhombic"
    assert mapi_ba.dimensionality == 3
    assert mapi_ba.sites
    assert mapi_ba.distances
    assert mapi_ba.angles
    assert mapi_ba.components
    assert mapi_ba.component_makeup
    assert mapi_ba.elements[0] == "H+"


def test_get_distance_details(tin_dioxide_ba, mapi_ba):
    # test get distance using int works
    distances = tin_dioxide_ba.get_distance_details(0, 2)
    assert len(distances), 3
    assert distances[0] == pytest.approx(2.0922101061490546)

    # test get distance using list works
    distances = tin_dioxide_ba.get_distance_details(0, [2])
    assert len(distances), 3
    assert distances[0] == pytest.approx(2.0922101061490546)

    # test getting multiple distances
    distances = mapi_ba.get_distance_details(44, [0, 8])
    assert len(distances), 4
    assert distances[0] == pytest.approx(1.0386222568611572)


def test_get_angle_details(tin_dioxide_ba):
    # test get angles using int works
    distances = tin_dioxide_ba.get_angle_details(0, 0, "corner")
    assert len(distances), 8
    assert distances[0] == pytest.approx(129.18849530149342)

    # test get angles using list works
    distances = tin_dioxide_ba.get_angle_details(0, [0], "corner")
    assert len(distances), 8
    assert distances[0] == pytest.approx(129.18849530149342)
