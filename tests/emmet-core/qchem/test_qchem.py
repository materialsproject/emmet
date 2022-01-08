import json

import pytest
from monty.io import zopen

from emmet.core.qchem.calc_types import LevelOfTheory, TaskType, level_of_theory, task_type
from emmet.core.qchem.task import TaskDocument

def test_task_type():

    task_types = [
        "single-point",
        "geometry optimization",
        "frequency analysis",
        "frequency-flattening geometry optimization",
        "transition-state geometry optimization",
        "frequency-flattening transition-state geometry optimization",
    ]

    inputs = [
        {"rem": {"job_type": "sp"}},
        {"rem": {"job_type": "opt"}},
        {"rem": {"job_type": "freq"}},
        {"rem": {"job_type": "opt"}},
        {"rem": {"job_type": "ts"}},
        {"rem": {"job_type": "freq"}},
    ]

    special_run_types = [
        None,
        None,
        None,
        "frequency_flattener",
        None,
        "ts_frequency_flattener",
    ]

    for _type, orig, special in zip(task_types, inputs, special_run_types):
        assert task_type(orig, special_run_type=special) == TaskType(_type)


def test_level_of_theory():
    lots = [
        "wB97X-V/def2-TZVPPD/SMD(EC/EMC)",
        "wB97X-D/def2-SVPD/PCM(WATER)",
        "wB97M-V/6-31g*/VACUUM"
    ]

    parameters = [
        {"rem": {"method": "wb97xv", "basis": "def2-tzvppd", "solvent_method": "smd"},
          "smx": {"solvent": "other"}},
         {"rem": {"method": "wb97xd", "basis": "def2-svpd", "solvent_method": "pcm"},
          "pcm": {"theory": "cpcm"},
          "solvent": {"dielectric": 78.39}},
         {"rem": {"method": "wb97mv", "basis": "6-31g*"}}
    ]

    custom_smd = [
        "18.5,1.415,0.0,0.735,20.2,0.0,0.0",
        None,
        None
    ]

    for lot, params, custom in zip(lots, parameters, custom_smd):
        assert level_of_theory(params, custom_smd=custom) == LevelOfTheory(lot)


def test_unexpected_lots():
    # No method provided
    with pytest.raises(ValueError):
        level_of_theory({"rem": {"basis": "def2-qzvppd"}})

    # No basis provided
    with pytest.raises(ValueError):
        level_of_theory({"rem": {"method": "b3lyp"}})

    # Unknown dispersion correction
    with pytest.raises(ValueError):
        level_of_theory({"rem": {"method": "b3lyp", "dft_d": "empirical_grimme"}})

    # Unknown functional
    with pytest.raises(ValueError):
        level_of_theory({"rem": {"method": "r2scan"}})

    # Unknown basis
    with pytest.raises(ValueError):
        level_of_theory({"rem": {"method": "wb97xd3", "basis": "aug-cc-pVTZ"}})

    # Unknown solvent for PCM
    with pytest.raises(ValueError):
        level_of_theory({"rem": {"method": "wb97xd", "basis": "def2-svpd", "solvent_method": "pcm"},
                         "pcm": {"theory": "cpcm"},
                         "solvent": {"dielectric": 3.2}})

    # # Unknown solvent for SMD, based on custom parameters
    # with pytest.raises(ValueError):
    #     pass
    #
    # # Unexpected solvent with given name
    # with pytest.raises(ValueError):
    #     pass
    #
    # # solvent=other for SMD, but no custom_smd provided
    # with pytest.raises(ValueError):
    #     pass