import datetime
import json
from pathlib import Path

import numpy as np
import pytest
from bson.objectid import ObjectId
from monty.json import MSONable
from monty.serialization import loadfn

from emmet.core.tasks import TaskDoc
from emmet.core.utils import (
    convert_datetime,
    dynamic_import,
    get_flat_models_from_model,
    get_hash_blocked,
    jsanitize,
    utcnow,
)


def test_dt():

    ref_dt = utcnow()

    for test_dt in (
        jsanitize(ref_dt),
        {"$date": jsanitize(ref_dt)},
    ):
        assert convert_datetime(test_dt) == ref_dt


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


def test_blocked_hash(tmp_dir):
    import blake3

    file_text = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, "
        "sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
    ).encode()

    with open("test_md5.gz", "wb") as f:
        f.write(file_text)

    assert get_hash_blocked("test_md5.gz") == blake3.blake3(file_text).hexdigest()


def test_model_flatten():

    sub_models = get_flat_models_from_model(TaskDoc)
    assert {model.__name__ for model in sub_models} == {
        "AnalysisDoc",
        "BaderAnalysis",
        "Calculation",
        "CalculationInput",
        "CalculationOutput",
        "CustodianDoc",
        "ElectronPhononDisplacedStructures",
        "ElectronicStep",
        "FrequencyDependentDielectric",
        "IonicStep",
        "OutputDoc",
        "PotcarSpec",
        "RunStatistics",
        "SymmetryData",
        "TaskDoc",
    }


def test_import():

    assert dynamic_import("emmet.core.tasks.TaskDoc") == TaskDoc


def test_data_archive(tmp_dir):

    from monty.io import zopen
    from emmet.core.testing_utils import DataArchive

    def listify_file(file_name):
        with zopen(file_name, "rt") as f:
            return list(f.read())

    test_str = "the quick brown fox jumped over the lazy dog"
    test_files = {"test_file", "test_gzipped.gz"}
    for p in test_files:
        with zopen(p, "wt") as f:
            f.write(test_str)

    archive = DataArchive.from_directory(".")

    archive_path = Path("test.json.gz")
    archive.to_json(archive_path)
    assert archive_path.is_file()
    loaded = loadfn(archive_path)
    assert set(loaded) == test_files
    assert loaded["test_file"]["0"] == test_str.encode().hex()

    with DataArchive.extract(archive_path) as temp_dir:
        assert {p.name for p in temp_dir.glob("*")} == test_files

    for fname in test_files:
        assert DataArchive.extract_obj(archive_path, fname, listify_file) == list(
            test_str
        )
