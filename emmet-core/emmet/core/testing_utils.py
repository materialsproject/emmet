"""Define common testing utils used across emmet namespaces."""

from __future__ import annotations

import math
from contextlib import contextmanager
from importlib.resources import files as import_resource
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from pydantic import BaseModel

from emmet.core.utils import arrow_incompatible

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from typing import Any

    from emmet.core.types.typing import FSPathType


def _get_test_files_dir(module: str) -> Path:
    """Get path to test files directory."""
    return (
        Path(import_resource(module))  # type: ignore[arg-type]
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


def assert_nested_close(
    test: Any,
    ref: Any,
    float_comparator: Callable = _float_comparator,
    _path: str = "",
) -> None:
    """
    Recursively assert that two (nested) objects are equal, up to float tolerance.

    Unlike `assert_schemas_equal`, this checks both directions: the objects
    must have the same keys / lengths. Pydantic models are compared by their
    `model_dump()`, and numpy arrays by value.

    Mainly useful to compare an object with its round-trip through a lossy
    format, such as float32 columns in arrow.

    Args:
        test : The object under test.
        ref : The reference object.
        float_comparator (Callable) : A method to compare floats. Defaults to
            math.isclose with rel_tol = 1e-6.
    """
    if isinstance(test, BaseModel):
        test = test.model_dump()
    if isinstance(ref, BaseModel):
        ref = ref.model_dump()
    if isinstance(test, np.ndarray):
        test = test.tolist()
    if isinstance(ref, np.ndarray):
        ref = ref.tolist()

    where = f" at `{_path}`" if _path else ""
    if isinstance(ref, dict):
        assert isinstance(test, dict) and set(test) == set(
            ref
        ), f"Keys differ{where}: {set(test) ^ set(ref) if isinstance(test, dict) else type(test)}"
        for k, v in ref.items():
            assert_nested_close(test[k], v, float_comparator, f"{_path}.{k}")
    elif isinstance(ref, list | tuple):
        assert isinstance(test, list | tuple) and len(test) == len(
            ref
        ), f"Lengths differ{where}"
        for i, v in enumerate(ref):
            assert_nested_close(test[i], v, float_comparator, f"{_path}[{i}]")
    elif isinstance(ref, float) and not isinstance(ref, bool):
        assert isinstance(test, int | float) and float_comparator(
            test, ref
        ), f"{test} != {ref}{where}"
    else:
        assert test == ref, f"{test} != {ref}{where}"


@arrow_incompatible
class DataArchive(BaseModel):
    """Tool to compress test data into a lower disk / innode use file."""

    files: dict[str, bytes]

    @classmethod
    def from_directory(cls, path: FSPathType):
        """Find all files in . and parse them."""

        files = {}
        for p in Path(path).glob("*"):
            if p.is_file():
                files[p.name] = p.read_bytes()
        return cls(files=files)

    def to_json(self, file_name: FSPathType) -> None:
        """Write all contents to JSON."""
        df = pd.DataFrame({k: [v.hex()] for k, v in self.files.items()})
        df.to_json(file_name, orient="columns")

    @staticmethod
    def from_json(archive_path: FSPathType) -> pd.DataFrame:
        df = pd.read_json(archive_path)
        for c in df.columns:
            df[c] = df[c].apply(bytes.fromhex)
        return df

    @classmethod
    @contextmanager  # type: ignore[arg-type]
    def extract(cls, archive_path: FSPathType) -> Generator[Path]:
        """Extract all bytes data from a JSON archive.

        Parameters
        -----------
        archive_path : FSPathType
            The name of the JSON file

        Returns
        -----------
        pandas DataFrame representing the parsed data.
        """

        df = cls.from_json(archive_path)
        temp_dir = TemporaryDirectory()
        base_path = Path(temp_dir.name)
        for c in df.columns:
            (base_path / c).write_bytes(df[c][0])

        try:
            yield base_path
        finally:
            temp_dir.cleanup()

    @staticmethod
    def extract_obj(
        archive_path: FSPathType, file_name: str, func: Callable, *args, **kwargs
    ) -> Any:
        """Extract a single file and apply a mapping to it."""
        df = pd.read_json(archive_path)
        if file_name not in df.columns:
            raise ValueError(
                f"No object {file_name} found, valid columns: {', '.join(df.columns)}"
            )

        temp_file = NamedTemporaryFile(suffix="".join(Path(file_name).suffixes))
        with open(temp_file.name, "wb") as f:
            f.write(bytes.fromhex(df[file_name][0]))
            f.seek(0)

        obj = func(temp_file.name, *args, **kwargs)
        temp_file.close()
        return obj
