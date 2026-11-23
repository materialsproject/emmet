import pytest
from fastapi import HTTPException

from emmet.api.query_operator import NumericQuery
from emmet.api.routes.materials.phonon.query_operators import (
    EnlargedSupercellQuery,
    PhononStabilityClassQuery,
)
from emmet.core.phonon import PhononBSDOSTask


def test_phonon_stability_class_query():
    op = PhononStabilityClassQuery()

    assert op.query(phonon_stability_class=None) == {"criteria": {}}
    assert op.query(phonon_stability_class="") == {"criteria": {}}
    assert op.query(phonon_stability_class="real_frequencies") == {
        "criteria": {"phonon_stability_class": {"$in": ["real_frequencies"]}}
    }
    assert op.query(phonon_stability_class="real_frequencies, gamma_artifact") == {
        "criteria": {
            "phonon_stability_class": {"$in": ["real_frequencies", "gamma_artifact"]}
        }
    }

    for bad in ("invalid", "   ", "real_frequencies,"):
        with pytest.raises(HTTPException) as exc_info:
            op.query(phonon_stability_class=bad)
        assert exc_info.value.status_code == 400


def test_enlarged_supercell_query():
    op = EnlargedSupercellQuery()

    assert op.query(enlarged_supercell_used=None) == {"criteria": {}}
    assert op.query(enlarged_supercell_used=True) == {
        "criteria": {"enlarged_supercell_used": True}
    }
    assert op.query(enlarged_supercell_used=False) == {
        "criteria": {"enlarged_supercell_used": False}
    }


def test_phonon_numeric_query_fields():
    op = NumericQuery(model=PhononBSDOSTask, excluded_fields=["composition"])
    for field_name in (
        "min_frequency",
        "max_frequency",
        "debye_temperature",
        "pheasy_fit_rmse",
        "pheasy_fit_relative_error",
    ):
        assert f"{field_name}_min" in op.mapping
        assert f"{field_name}_max" in op.mapping

    assert op.query(min_frequency_min=-0.1, debye_temperature_max=500.0) == {
        "criteria": {
            "min_frequency": {"$gte": -0.1},
            "debye_temperature": {"$lte": 500.0},
        }
    }
