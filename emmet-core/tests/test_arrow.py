import importlib
import inspect
import itertools
import os
from pathlib import Path
from typing import Annotated, Optional, Union

import pytest
from pydantic import BaseModel
from pydantic._internal._model_construction import ModelMetaclass

from emmet.core import ARROW_COMPATIBLE

pa = pytest.importorskip("pyarrow")

if ARROW_COMPATIBLE:
    from emmet.core.arrow import (
        ArrowType,
        Float32Grid,
        Float32List,
        Float32Matrix,
        arrowize,
    )


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
            arrowize(Optional[int]),  # noqa: UP045
            arrowize(Union[int | None]),  # noqa: UP007
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


def test_arrowize_arrow_type_override():
    assert arrowize(Float32List) == pa.list_(pa.float32())
    assert arrowize(Float32Grid) == pa.large_list(pa.float32())
    assert arrowize(Float32Matrix) == pa.list_(pa.list_(pa.float32()))

    # optional forms
    assert arrowize(Float32Grid | None) == pa.large_list(pa.float32())
    assert arrowize(Optional[Float32Grid]) == pa.large_list(pa.float32())  # noqa: UP045

    # nested, as in ChgcarLike.data
    assert arrowize(list[Float32Grid | None] | None) == pa.list_(
        pa.large_list(pa.float32())
    )

    # custom marker
    custom = Annotated[str, ArrowType(lambda: pa.large_string())]
    assert arrowize(custom) == pa.large_string()

    # unrelated Annotated metadata is still ignored
    assert arrowize(Annotated[int, "foo"]) == pa.int64()


def test_arrowize_arrow_type_override_model_roundtrip():
    class _Model(BaseModel):
        grid: Float32Grid | None = None
        nested: list[Float32Grid | None] | None = None
        energy: float | None = None

    schema = pa.schema(arrowize(_Model))
    assert schema.field("grid").type == pa.large_list(pa.float32())
    assert schema.field("nested").type == pa.list_(pa.large_list(pa.float32()))
    assert schema.field("energy").type == pa.float64()

    model = _Model(grid=[0.1, 0.25, 3.0], nested=[[1.5, 2.5], None], energy=0.1)

    # pydantic validation / serialization is unaffected by the marker
    dumped = model.model_dump()
    assert dumped["grid"] == [0.1, 0.25, 3.0]

    table = pa.Table.from_pylist([dumped, _Model().model_dump()], schema=schema)
    assert table.schema == schema

    rows = table.to_pylist()
    restored = _Model(**rows[0])
    assert restored.grid == pytest.approx(model.grid, rel=1e-6)
    assert restored.nested[0] == pytest.approx(model.nested[0], rel=1e-6)
    assert restored.nested[1] is None
    assert restored.energy == model.energy
    assert _Model(**rows[1]) == _Model()
