import importlib
import inspect
import os
from typing import Optional, Union

import pyarrow as pa
import pytest
from pydantic._internal._model_construction import ModelMetaclass

from emmet.core import core_path
from emmet.core.arrow import arrowize


def import_models():
    core_models = []
    files = os.listdir(core_path)
    for file in files:
        if file not in ["__init__.py", "__pycache__"]:
            if file[-3:] != ".py":
                continue

            file_name = file[:-3]
            module_name = "emmet.core" + "." + file_name

            for name, obj in inspect.getmembers(
                importlib.import_module(module_name), inspect.isclass
            ):
                if obj.__module__ == module_name and isinstance(obj, ModelMetaclass):
                    core_models.append(obj)

    return core_models


def test_arrowize_succeeds():
    assert all(
        dtype == pa.int64()
        for dtype in [
            arrowize(int | None),
            arrowize(Optional[int]),
            arrowize(Union[int | None]),
        ]
    )

    assert all(
        dtype == pa.map_(pa.string(), pa.int64())
        for dtype in [arrowize(dict[str, int])]
    )

    # assert arrowize(set([10, 20, 30])) == pa.list_(pa.int64())


def test_arrowize_fails():
    with pytest.raises(AssertionError):
        arrowize(int | str)
        arrowize(dict)
        arrowize(list)
        arrowize(tuple)


@pytest.mark.parametrize("model", import_models())
def test_document_models_for_arrow_compatibility(model):
    assert isinstance(arrowize(model), pa.DataType)
