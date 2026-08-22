"""Test symmetry-related utilities."""

from emmet.core.io.pymatgen import SYMM_DATA
import pytest

from emmet.core.symmetry import (
    _get_space_group_symbol_to_number_mapping,
    get_crystal_system_from_international_number,
    CrystalSystem,
    _get_number_to_space_group_symbol_mapping,
)


def test_spacegroup_symbol_number_mapping():

    sgsn = _get_space_group_symbol_to_number_mapping()
    assert all(isinstance(k, str) and isinstance(v, int) for k, v in sgsn.items())
    assert all(
        sgsn.get(k) == v
        and get_crystal_system_from_international_number(v) == CrystalSystem.cubic
        for k, v in {
            "Fm-3m": 225,
            "Im-3m": 229,
            "Ia-3d": 230,
        }.items()
    )

    assert all(k in sgsn for k in SYMM_DATA["abbreviated_spacegroup_symbols"])
    assert sorted(set(sgsn.values())) == list(range(1, 231))


def test_get_crystal_system():

    for sgn in range(232):
        if sgn < 1 or sgn > 230:
            with pytest.raises(ValueError, match="Invalid space group number"):
                get_crystal_system_from_international_number(sgn)
        else:
            assert isinstance(
                get_crystal_system_from_international_number(sgn), CrystalSystem
            )


@pytest.mark.parametrize(
    "space_group_number, expected_symbol",
    [
        (15, "C2/c"),
        (12, "C2/m"),
        (5, "C2"),
        (9, "Cc"),
        (8, "Cm"),
        (13, "P2/c"),
        (10, "P2/m"),
        (3, "P2"),
        (14, "P2_1/c"),
        (11, "P2_1/m"),
        (4, "P2_1"),
        (7, "Pc"),
        (6, "Pm"),
        (39, "Aem2"),
        (41, "Aea2"),
        (67, "Cmme"),
        (68, "Ccce"),
    ],
)
def test_get_number_to_space_group_symbol_mapping(space_group_number, expected_symbol):
    mapping = _get_number_to_space_group_symbol_mapping()
    assert mapping[space_group_number] == expected_symbol, (
        f"Mismatch for space group {space_group_number}: "
        f"expected '{expected_symbol}', got '{mapping.get(space_group_number)}'. "
        "If this fails, check recent changes to "
        "_get_space_group_symbol_to_number_mapping() — most likely "
        "SYMM_DATA['abbreviated_spacegroup_symbols'] has been modified."
    )
