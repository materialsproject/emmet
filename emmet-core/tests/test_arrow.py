import importlib
import inspect
import itertools
import os
from pathlib import Path
from typing import Optional, Union

import pytest
from pydantic._internal._model_construction import ModelMetaclass

from emmet.core import ARROW_COMPATIBLE

pa = pytest.importorskip("pyarrow")

if ARROW_COMPATIBLE:
    from emmet.core.arrow import arrowize


def import_models():
    core_path = Path(__file__).parent.parent.joinpath("emmet/core")
    core_models = []
    for root, dirs, files in os.walk(core_path):
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")

        parent_module = ".".join(
            [
                "emmet",
                "core",
                *list(
                    itertools.takewhile(
                        lambda x: x != "core", reversed(root.split("/"))
                    )
                )[::-1],
            ]
        )

        for file in files:
            if file not in ["__init__.py", "__pycache__"]:
                if file[-3:] != ".py":
                    continue

                file_name = file[:-3]
                if file_name == "optimade":
                    continue
                module_name = f"{parent_module}.{file_name}"

                for name, obj in inspect.getmembers(
                    importlib.import_module(module_name), inspect.isclass
                ):
                    if (
                        obj.__module__ == module_name
                        and isinstance(obj, ModelMetaclass)
                        and not hasattr(obj, "arrow_incompatible")
                    ):
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
        for dtype in [arrowize(dict[str, int]), arrowize(dict[str, int | None])]
    )


def test_arrowize_fails():
    with pytest.raises(AssertionError):
        arrowize(dict)
        arrowize(list)
        arrowize(tuple)


@pytest.mark.parametrize("model", import_models())
def test_document_models_for_arrow_compatibility(model):
    assert isinstance(arrowize(model), pa.DataType)
