import pytest

from emmet.core.featurization.robocrys.condense.mineral import MineralMatcher


@pytest.fixture
def matcher():
    return MineralMatcher()


@pytest.fixture
def tin_dioxide(test_structures):
    return test_structures["SnO2"].copy()


@pytest.fixture
def double_perov(test_structures):
    return test_structures["double_perovskite"].copy()


def test_get_aflow_matches(matcher, tin_dioxide):
    """Test AFLOW prototype matching."""
    matches = matcher.get_aflow_matches(tin_dioxide)

    assert len(matches) == 1, "number of matches is not equal to 1"
    assert matches[0]["type"] == "Rutile", "SnO2 mineral name incorrect"
    assert matches[0]["distance"] == pytest.approx(
        0.15047694852244528
    ), "SnO2 fingerprint distance does not match"
    assert matches[0].get("structure"), "SnO2 structure not present in match dictionary"


def test_get_fingerprint_matches(matcher, tin_dioxide, double_perov):
    """Test fingerprint based matching."""
    matches = matcher.get_fingerprint_matches(tin_dioxide)
    assert len(matches) == 4, "number of matches is not equal to 1"
    assert matches[0]["type"] == "Hydrophilite", "SnO2 mineral name incorrect"
    assert matches[0]["distance"] == pytest.approx(
        0.1429748846147379
    ), "SnO2 fingerprint distance does not match"
    assert matches[0].get("structure"), "SnO2 structure not present in match dictionary"

    # test fingerprint only matches same number of atoms
    matches = matcher.get_fingerprint_matches(double_perov)
    assert matches is None

    # test fingerprint can match different number of atoms
    matches = matcher.get_fingerprint_matches(double_perov, match_n_sp=False)
    assert len(matches) == 1, "double perovskite number of matches not correct"
    assert (
        matches[0]["type"] == "(Cubic) Perovskite"
    ), "Double perovskite mineral name incorrect"
    assert matches[0]["distance"] == pytest.approx(
        0.11697185
    ), "double perovskite fingerprint distance does not match"
    assert matches[0].get(
        "structure"
    ), "perovskite structure not present in match dictionary"


def test_get_best_mineral_name(matcher, tin_dioxide, double_perov):
    """Test mineral name matching."""
    mineral_data = matcher.get_best_mineral_name(tin_dioxide)
    assert mineral_data["type"] == "Rutile"
    assert mineral_data["distance"] == -1.0
    assert mineral_data["n_species_type_match"] is True

    mineral_data = matcher.get_best_mineral_name(double_perov)
    assert mineral_data["type"] == "(Cubic) Perovskite"
    assert mineral_data["distance"] == pytest.approx(0.116971854532)
    assert mineral_data["n_species_type_match"] is False
