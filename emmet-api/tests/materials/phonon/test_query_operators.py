import pytest
from fastapi import HTTPException

from emmet.api.query_operator import NumericQuery
from emmet.api.routes.materials.phonon.query_operators import (
    EnlargedSupercellQuery,
    HasNacQuery,
    NoNacReasonQuery,
    PheasyFitRouteQuery,
    PhononStabilityClassQuery,
    PhononVersionQuery,
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


def test_pheasy_fit_route_query():
    op = PheasyFitRouteQuery()

    assert op.query(pheasy_fit_route=None) == {"criteria": {}}
    assert op.query(pheasy_fit_route="") == {"criteria": {}}
    assert op.query(pheasy_fit_route="ASR + BH(dipole) + H(dipole)") == {
        "criteria": {"pheasy_fit_route": {"$in": ["ASR + BH(dipole) + H(dipole)"]}}
    }
    assert op.query(pheasy_fit_route="ASR, ASR + BH + H") == {
        "criteria": {"pheasy_fit_route": {"$in": ["ASR", "ASR + BH + H"]}}
    }

    for bad in ("invalid", "   ", "ASR,"):
        with pytest.raises(HTTPException) as exc_info:
            op.query(pheasy_fit_route=bad)
        assert exc_info.value.status_code == 400


def test_has_nac_query():
    op = HasNacQuery()

    assert op.query(has_nac=None) == {"criteria": {}}
    assert op.query(has_nac=True) == {"criteria": {"has_nac": True}}
    assert op.query(has_nac=False) == {"criteria": {"has_nac": False}}


def test_no_nac_reason_query():
    op = NoNacReasonQuery()

    assert op.query(no_nac_reason=None) == {"criteria": {}}
    assert op.query(no_nac_reason="") == {"criteria": {}}
    assert op.query(no_nac_reason="no_dielectric_run") == {
        "criteria": {"no_nac_reason": {"$in": ["no_dielectric_run"]}}
    }
    assert op.query(no_nac_reason="no_dielectric_run, identity_dielectric_tensor") == {
        "criteria": {
            "no_nac_reason": {
                "$in": ["no_dielectric_run", "identity_dielectric_tensor"]
            }
        }
    }

    for bad in ("invalid", "   ", "no_dielectric_run,"):
        with pytest.raises(HTTPException) as exc_info:
            op.query(no_nac_reason=bad)
        assert exc_info.value.status_code == 400


def test_phonon_version_query():
    op = PhononVersionQuery()

    assert op.query(version=None) == {"criteria": {}}
    assert op.query(version="") == {"criteria": {}}
    assert op.query(version="v1.2") == {"criteria": {"version": {"$in": ["v1.2"]}}}
    assert op.query(version="v1.1, v1.2") == {
        "criteria": {"version": {"$in": ["v1.1", "v1.2"]}}
    }
