import pytest

from emmet.core.qchem.solvent import (
    parse_custom_string,
    custom_string,
    clean_custom_string,
    SolventModel,
    SolventData
)


def test_smx_string():
    initial_string = "7.23,1.4097,0.00,0.859,36.83,0.00,0.00"

    smx_values_dict = {
        "dielectric": 7.23,
        "refractive_index": 1.4097,
        "abraham_acidity": 0.0,
        "abraham_basicity": 0.859,
        "surface_tension": 36.83,
        "aromaticity": 0.0,
        "halogenicity": 0.0
    }

    assert parse_custom_string(initial_string) == smx_values_dict

    assert custom_string(smx_values_dict) == clean_custom_string(initial_string)
    assert clean_custom_string(initial_string) == "7.23,1.4097,0.0,0.859,36.83,0.0,0.0"


def test_construct_solvent_data():

    with pytest.raises(ValueError):
        _ = SolventData.from_inputs(dict())

    sd_no_solvent = SolventData.from_inputs(
        {"rem": {"method": "wb97xd", "basis": "6-311++g(d,p)"}}
    )
    assert sd_no_solvent.name == "vacuum"
    assert sd_no_solvent.model == SolventModel("vacuum")

    sd_smx = SolventData.from_inputs(
        {
            "rem": {"method": "wb97xd", "basis": "6-311++g(d,p)", "solvent_method": "smd"},
            "smx": {"solvent": "thf"}
        }
    )
    assert sd_smx.name == "Tetrahydrofuran"
    assert sd_smx.model == SolventModel("SMX")

    sd_custom = SolventData.from_inputs(
        {
            "rem": {"method": "wb97xd", "basis": "6-311++g(d,p)", "solvent_method": "smd"},
            "smx": {"solvent": "other"}
        },
        metadata={"custom_smd": "7.23,1.4097,0.00,0.859,36.83,0.00,0.00"}
    )
    assert sd_custom.name == "Diglyme"
    assert sd_custom.model == SolventModel("SMX")
    assert sd_custom.dielectric == 7.23
    assert sd_custom.refractive_index == 1.4097
    assert sd_custom.abraham_acidity == 0.0
    assert sd_custom.abraham_basicity == 0.859
    assert sd_custom.surface_tension == 36.83
    assert sd_custom.aromaticity == 0.0
    assert sd_custom.halogenicity == 0.0

    sd_pcm = SolventData.from_inputs(
        {
            "rem": {"method": "wb97xd", "basis": "6-311++g(d,p)", "solvent_method": "pcm"},
            "pcm": {"theory": "cosmo"},
            "solvent": {"dielectric": 7.23}
        }
    )
    assert sd_pcm.name == "Diglyme"
    assert sd_pcm.model == SolventModel("PCM")
    assert sd_pcm.dielectric == 7.23
    assert sd_pcm.pcm_params == {"theory": "cosmo", "dielectric": 7.23}

