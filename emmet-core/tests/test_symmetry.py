"""Test symmetry-related utilities."""

from pymatgen.symmetry.groups import SYMM_DATA
import pytest

from emmet.core.symmetry import (
    _get_space_group_symbol_to_number_mapping,
    get_crystal_system_from_international_number,
    CrystalSystem,
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
