from __future__ import annotations

import pytest

from emmet.core.featurization.robocrys.condense.fingerprint import (
    get_fingerprint_distance,
    get_site_fingerprints,
    get_structure_fingerprint,
)


@pytest.fixture
def fe(test_structures):
    return test_structures["iron"].copy()


def test_get_site_fingerprints(fe):
    """Test to check site fingerprinting."""
    finger = get_site_fingerprints(fe)[0]
    assert finger["body-centered cubic CN_8"] == pytest.approx(0.576950507)

    # check as_dict option
    finger = get_site_fingerprints(fe, as_dict=False)[0]
    assert finger[30] == pytest.approx(0.576950507)


def test_get_structure_fingerprint(fe):
    """Test to check structure fingerprinting."""
    fingerprint = get_structure_fingerprint(fe)
    assert fingerprint[4] == pytest.approx(1.98432036e-03)

    # test stats option
    fingerprint = get_structure_fingerprint(fe, stats=("mean",))
    assert fingerprint[31] == pytest.approx(2.51322893e-01)


def test_get_fingerprint_distance(fe):
    """Tests to check getting fingerprint distance."""
    finger_1 = [0, 0, 0, 1]
    finger_2 = [1, 0, 0, 0]
    dist = get_fingerprint_distance(finger_1, finger_2)
    assert dist == pytest.approx(1.4142135623730951)

    # test automatic conversion from structure to fingerprint
    dist = get_fingerprint_distance(fe, fe)
    assert dist == pytest.approx(0.0)

    # test one structure one fingerprint
    finger_1 = get_structure_fingerprint(fe)
    dist = get_fingerprint_distance(fe, finger_1)
    assert dist == pytest.approx(0.0)
