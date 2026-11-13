import subprocess
import sys
import textwrap

import numpy as np
import pyarrow as pa
import pytest
from pydantic import BaseModel, ValidationError

from emmet.core.arrow import arrowize
from emmet.core.types.arrow_annotations import Float32Array, Float64Array


def test_arrow_annotations_do_not_require_pyarrow():
    """Models can use the arrow annotations when pyarrow is not installed."""
    code = textwrap.dedent(
        """
        import sys

        # make `import pyarrow` fail, as if it were not installed
        sys.modules["pyarrow"] = None

        from pydantic import BaseModel

        from emmet.core.types.arrow_annotations import ArrowType, Float32Grid

        class Model(BaseModel):
            grid: Float32Grid | None = None

        model = Model(grid=[0.1, 0.2])
        assert model.model_dump() == {"grid": [0.1, 0.2]}
        assert Model.model_validate_json(model.model_dump_json()) == model

        # pyarrow is only needed once the arrow type is actually requested
        try:
            ArrowType(lambda: __import__("pyarrow")).dtype
        except ImportError:
            pass
        else:
            raise AssertionError("expected ImportError")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_array_annotations_do_not_require_pyarrow():
    """The array types, which hold numpy arrays, are usable without pyarrow too."""
    code = textwrap.dedent(
        """
        import sys

        sys.modules["pyarrow"] = None

        import numpy as np
        from pydantic import BaseModel

        from emmet.core.types.arrow_annotations import Float32Array, Float64Array

        class Model(BaseModel):
            a: Float32Array | None = None
            b: Float64Array | None = None

        model = Model(a=[0.5, 1.5], b=np.arange(3.0))
        assert model.model_dump() == {"a": [0.5, 1.5], "b": [0.0, 1.0, 2.0]}
        assert model.a.dtype == np.float32 and model.b.dtype == np.float64
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


class TestArrayAnnotations:
    @pytest.fixture
    def model(self):
        class Model(BaseModel):
            single: Float32Array | None = None
            double: Float64Array | None = None

        return Model

    def test_values_are_held_as_arrays_of_their_type(self, model):
        row = model(single=[1.5, 2.5], double=np.arange(3, dtype=np.float32))
        assert row.single.dtype == np.float32 and row.double.dtype == np.float64
        assert isinstance(row.single, np.ndarray)
        # a value takes the bytes of its type, where a list takes about 32
        big = model(single=np.zeros(100_000), double=np.zeros(100_000))
        assert big.single.nbytes == 4 * 100_000 and big.double.nbytes == 8 * 100_000

    def test_an_array_of_the_right_type_is_not_copied(self, model):
        array = np.arange(10, dtype=np.float32)
        assert np.shares_memory(model(single=array).single, array)
        # one of another type is made the type of the field
        assert model(single=np.arange(10.0)).single.dtype == np.float32

    def test_none_is_kept(self, model):
        row = model()
        assert row.single is None and row.double is None
        assert row.model_dump() == {"single": None, "double": None}

    @pytest.mark.parametrize("shape", [(2, 2), (2, 2, 2)])
    def test_only_flat_arrays(self, model, shape):
        with pytest.raises(ValidationError):
            model(single=np.zeros(shape))

    def test_a_dump_is_lists_but_the_dump_for_arrow_is_the_array(self, model):
        row = model(single=[0.5, 1.5], double=[2.0])
        assert row.model_dump() == {"single": [0.5, 1.5], "double": [2.0]}
        assert type(row.model_dump()["single"]) is list
        assert row.model_dump_json() == '{"single":[0.5,1.5],"double":[2.0]}'
        arrow = row.model_dump(context={"format": "arrow"})
        assert isinstance(arrow["single"], np.ndarray) and arrow["single"] is row.single

    def test_a_list_assigned_without_validation_still_dumps(self, model):
        row = model(single=[1.0]).model_copy(update={"single": [3.0, 4.0]})
        assert row.model_dump()["single"] == [3.0, 4.0]

    def test_values_come_back_from_a_dump_and_from_arrow(self, model):
        row = model(single=[0.25, 0.5], double=[1.0, 2.0])
        assert model(**row.model_dump()).single.dtype == np.float32
        table = pa.Table.from_pylist(
            [row.model_dump(context={"format": "arrow"})],
            schema=pa.schema(arrowize(model)),
        )
        back = model(**table.to_pylist()[0])
        np.testing.assert_array_equal(back.single, row.single)
        np.testing.assert_array_equal(back.double, row.double)

    def test_the_arrow_types_are_large_lists_of_their_type(self, model):
        schema = pa.schema(arrowize(model))
        assert schema.field("single").type == pa.large_list(pa.float32())
        assert schema.field("double").type == pa.large_list(pa.float64())

    def test_the_json_schema_is_an_array_of_numbers(self, model):
        properties = model.model_json_schema()["properties"]
        assert {"type": "array", "items": {"type": "number"}} in properties["single"][
            "anyOf"
        ]
