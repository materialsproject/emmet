import json

import pytest
from monty.io import zopen
from monty.serialization import loadfn

from emmet.core.jaguar.calc_types import (
    LevelOfTheory,
    TaskType,
    level_of_theory,
    task_type,
)
from emmet.core.jaguar.task import TaskDocument


def test_task_type():

    task_types = [
        "Single Point",
        "Geometry Optimization",
        "Frequency Analysis",
        "Transition State Geometry Optimization",
        "Intrinsic Reaction Coordinate",
        "Potential Energy Surface Scan",
    ]

    inputs = ["sp", "opt", "freq", "ts", "irc", "scan"]

    for _type, inp in zip(task_types, inputs):
        assert task_type(inp) == TaskType(_type)


def test_level_of_theory():
    lots = [
        "wb97x-v/def2-tzvppd(-g)/VACUUM",
        "wb97x-d/def2-svpd(-f)/PCM(WATER)",
    ]

    parameters = [
        {"gen_variables": {"dftname": "wb97x-v", "basis": "def2-tzvppd(-g)"}},
        {
            "gen_variables": {"dftname": "wb97x-d", "basis": "def2-svpd(-f)"},
            "solvation": True,
        },
    ]

    for lot, params in zip(lots, parameters):
        assert level_of_theory(params) == LevelOfTheory(lot)


def test_unexpected_lots():
    # No method provided
    with pytest.raises(ValueError):
        level_of_theory({"gen_variables": {"basis": "def2-tzvppd(-g)"}})

    # No basis provided
    with pytest.raises(ValueError):
        level_of_theory({"gen_variables": {"dftname": "CAM-B3LYP-D3"}})

    # Unknown functional
    with pytest.raises(ValueError):
        level_of_theory(
            {"gen_variables": {"dftname": "b3lyp", "basis": "def2-svpd(-f)"}}
        )

    # Unknown basis
    with pytest.raises(ValueError):
        level_of_theory(
            {"gen_variables": {"dftname": "wb97x-d", "basis": "6-31+g(d,p)"}}
        )


@pytest.fixture(scope="session")
def task(test_dir):
    task = loadfn((test_dir / "jaguar" / "test_ts_39.json").as_posix())

    return TaskDocument(**task)


def test_entry(task):
    entry = task.entry

    assert entry["entry_id"] == 39
    assert entry["nelectrons"] == 97
    assert entry["charge"] == -1
    assert entry["task_type"] == "Transition State Geometry Optimization"
    assert entry["input"]["gen_variables"]["inhess"] == 4
    assert entry["output"]["frequencies"][0] < -491
