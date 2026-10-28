import subprocess
import sys
import textwrap


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
