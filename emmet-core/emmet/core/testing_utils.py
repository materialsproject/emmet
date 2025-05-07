"""Define common testing utils used across emmet namespaces."""
from __future__ import annotations

from importlib.resources import files as import_resource
import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


def _get_test_files_dir(module: str) -> Path:
    """Get path to test files directory."""
    return (
        Path(str(import_resource(module)))
        .parent.parent.parent.joinpath("test_files")
        .resolve()
    )


TEST_FILES_DIR = _get_test_files_dir("emmet.core")
"""Test files directory measured relative to emmet-core install."""


def _float_comparator(x: float, y: float):
    """Compare floats with defaults set to pytest.approx defaults."""
    return math.isclose(x, y, rel_tol=1e-6, abs_tol=1e-12)


def assert_schemas_equal(
    test_schema: Any, valid_schema: Any, float_comparator: Callable = _float_comparator
) -> None:
    """
    Recursively test all items in valid_schema are present and equal in test_schema.

    While test_schema can be a pydantic schema or dictionary, the valid schema must
    be a (nested) dictionary. This function automatically handles accessing the
    attributes of classes in the test_schema.

    Args:
        test_schema: A pydantic schema or dictionary of the schema.
        valid_schema: A (nested) dictionary specifying the key and values that must be
            present in test_schema.
        float_comparator (Callable) : A method to compare floats. Defaults to math.isclose.
            Should return a bool if two floats are approximately equal, and False otherwise.
    """

    if isinstance(valid_schema, dict):
        for key, sub_valid_schema in valid_schema.items():
            if isinstance(key, str) and hasattr(test_schema, key):
                sub_test_schema = getattr(test_schema, key, {})
                if key in ("initial_molecule", "optimized_molecule") and hasattr(
                    sub_test_schema, "as_dict"
                ):
                    sub_test_schema = sub_test_schema.as_dict()

            elif not isinstance(test_schema, BaseModel):
                sub_test_schema = test_schema[key]
            else:
                raise ValueError(f"{type(test_schema)} does not have field: {key}")
            return assert_schemas_equal(sub_test_schema, sub_valid_schema)

    elif isinstance(valid_schema, list):
        for i, sub_valid_schema in enumerate(valid_schema):
            return assert_schemas_equal(test_schema[i], sub_valid_schema)

    elif isinstance(valid_schema, np.ndarray):
        assert np.allclose(test_schema, valid_schema)

    elif isinstance(valid_schema, float):
        assert float_comparator(test_schema, valid_schema)
    else:
        assert test_schema == valid_schema
