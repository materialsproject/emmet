import json

import pytest
from monty.io import zopen
from monty.serialization import loadfn

from emmet.core.qchem.calc_types import (
    LevelOfTheory,
    TaskType,
    level_of_theory,
    task_type,
)
from emmet.core.qchem.task import TaskDocument
from emmet.core.mpid import MPID


def test_task_type():

    task_types = [
        "Single Point",
        "Geometry Optimization",
        "Frequency Analysis",
        "Frequency Flattening Geometry Optimization",
        "Transition State Geometry Optimization",
        "Frequency Flattening Transition State Geometry Optimization",
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
        "wB97M-V/6-31g*/VACUUM",
    ]

    parameters = [
        {
            "rem": {
                "method": "wb97xv",
                "basis": "def2-tzvppd",
                "solvent_method": "smd",
            },
            "smx": {"solvent": "other"},
        },
        {
            "rem": {"method": "wb97xd", "basis": "def2-svpd", "solvent_method": "pcm"},
            "pcm": {"theory": "cpcm"},
            "solvent": {"dielectric": 78.39},
        },
        {"rem": {"method": "wb97mv", "basis": "6-31g*"}},
    ]

    custom_smd = ["18.5,1.415,0.0,0.735,20.2,0.0,0.0", None, None]

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
        level_of_theory(
            {
                "rem": {
                    "method": "wb97xd",
                    "basis": "def2-svpd",
                    "solvent_method": "pcm",
                },
                "pcm": {"theory": "cpcm"},
                "solvent": {"dielectric": 3.2},
            }
        )

    # Unknown solvent for SMD, based on custom parameters
    with pytest.raises(ValueError):
        level_of_theory(
            {
                "rem": {
                    "method": "wb97xv",
                    "basis": "def2-tzvppd",
                    "solvent_method": "smd",
                },
                "smx": {"solvent": "other"},
            },
            custom_smd="4.9,1.558,0.0,0.576,49.94,0.667,0.0",
        )

    # Unexpected solvent with given name
    with pytest.raises(ValueError):
        level_of_theory(
            {
                "rem": {
                    "method": "wb97xv",
                    "basis": "def2-tzvppd",
                    "solvent_method": "smd",
                },
                "smx": {"solvent": "cyclohexane"},
            }
        )

    # solvent=other for SMD, but no custom_smd provided
    with pytest.raises(ValueError):
        level_of_theory(
            {
                "rem": {
                    "method": "wb97xv",
                    "basis": "def2-tzvppd",
                    "solvent_method": "smd",
                },
                "smx": {"solvent": "other"},
            }
        )


@pytest.fixture(scope="session")
def tasks(test_dir):
    data = loadfn((test_dir / "random_bh4_entries.json.gz").as_posix())

    return [TaskDocument(**d) for d in data]


def test_computed_entry(tasks):
    entries = [task.entry for task in tasks]
    ids = {e["entry_id"] for e in entries}
    expected = {
        MPID(i)
        for i in {
            675022,
            674849,
            674968,
            674490,
            674950,
            674338,
            674322,
            675078,
            674385,
            675041,
        }
    }
    assert ids == expected
