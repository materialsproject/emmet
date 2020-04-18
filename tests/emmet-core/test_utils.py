import os
import unittest
import numpy as np
import json
import datetime
from bson.objectid import ObjectId
from enum import Enum

from monty.json import MSONable

import pytest
from emmet.core.utils import get_sg, group_structures, run_type, task_type, jsanitize


def test_jsanitize():
    """
    Tests emmet Jsanitize which converts MSONable classes into dicts
    """
    # clean_json should have no effect on None types.
    d = {"hello": 1, "world": None}
    clean = jsanitize(d)
    assert clean["world"] is None
    assert json.loads(json.dumps(d)) == json.loads(json.dumps(clean))

    d = {"hello": GoodMSONClass(1, 2, 3)}
    with pytest.raises(TypeError):
        json.dumps(d)

    clean = jsanitize(d)
    assert isinstance(clean["hello"], dict)
    clean_strict = jsanitize(d, strict=True)
    assert clean_strict["hello"]["a"] == 1
    assert clean_strict["hello"]["b"] == 2

    d = {"dt": datetime.datetime.now()}
    clean = jsanitize(d)
    assert isinstance(clean["dt"], str)
    clean = jsanitize(d, allow_bson=True)
    assert isinstance(clean["dt"], datetime.datetime)

    d = {
        "a": ["b", np.array([1, 2, 3])],
        "b": ObjectId.from_datetime(datetime.datetime.now()),
    }
    clean = jsanitize(d)
    assert clean["a"] == ["b", [1, 2, 3]]
    assert isinstance(clean["b"], str)

    rnd_bin = bytes(np.random.rand(10))
    d = {"a": bytes(rnd_bin)}
    clean = jsanitize(d, allow_bson=True)
    assert clean["a"] == bytes(rnd_bin)
    assert isinstance(clean["a"], bytes)


class GoodMSONClass(MSONable):
    def __init__(self, a, b, c, d=1, **kwargs):
        self.a = a
        self.b = b
        self._c = c
        self._d = d
        self.kwargs = kwargs

    def __eq__(self, other):
        return (
            self.a == other.a
            and self.b == other.b
            and self._c == other._c
            and self._d == other._d
            and self.kwargs == other.kwargs
        )


def test_task_tye():

    # TODO: Switch this to actual inputs?
    input_types = [
        ("NSCF Line", {"incar": {"ICHARG": 11}, "kpoints": {"labels": ["A"]}}),
        ("NSCF Uniform", {"incar": {"ICHARG": 11}}),
        ("Dielectric", {"incar": {"LEPSILON": True}}),
        ("DFPT Dielectric", {"incar": {"LEPSILON": True, "IBRION": 7}}),
        ("DFPT Dielectric", {"incar": {"LEPSILON": True, "IBRION": 8}}),
        ("DFPT", {"incar": {"IBRION": 7}}),
        ("DFPT", {"incar": {"IBRION": 8}}),
        ("Static", {"incar": {"NSW": 0}}),
    ]

    for _type, inputs in input_types:
        assert task_type(inputs) == _type


def test_run_type():

    params_sets = [
        ("GGA", {"GGA": "--"}),
        ("GGA+U", {"GGA": "--", "LDAU": True}),
        ("SCAN", {"METAGGA": "Scan"}),
        ("SCAN+U", {"METAGGA": "Scan", "LDAU": True}),
    ]

    for _type, params in params_sets:
        assert run_type(params) == _type
