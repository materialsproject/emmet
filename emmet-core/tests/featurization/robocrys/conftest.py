from monty.serialization import loadfn
from monty.json import MontyDecoder
from pathlib import Path
from pymatgen.core import Structure
import pytest
from typing import Any

from emmet.core.testing_utils import TEST_FILES_DIR


def _load_condensed_structure_json(filename: str | Path) -> dict[str, Any]:
    """Load condensed structure data from a file.

    Args:
        filename: The filename.

    Returns:
        The condensed structure data.
    """

    # JSON does not support using integers a dictionary keys, therefore
    # manually convert dictionary keys from str to int if possible.
    def json_keys_to_int(x: Any) -> Any:
        if isinstance(x, dict):
            return {
                int(k) if k.isdigit() else k: json_keys_to_int(v) for k, v in x.items()
            }
        return x

    # For some reason, specifying `object_hook = json_keys_to_int` in `loadfn`
    # doesn't seem to work. This does reliably:
    return json_keys_to_int(loadfn(filename, cls=MontyDecoder))


_robo_test_dir = TEST_FILES_DIR / "robocrys"


@pytest.fixture
def robo_test_dir():
    return _robo_test_dir


_test_structures = {}
for file_name in (_robo_test_dir / "structures").glob("*.json.gz"):
    _test_structures[file_name.name.split(".", 1)[0]] = Structure.from_file(file_name)

_test_condensed_structures = {}
for file_name in (_robo_test_dir / "condensed_structures").glob("*.json.gz"):
    _test_condensed_structures[file_name.name.split(".", 1)[0]] = (
        _load_condensed_structure_json(file_name)
    )


@pytest.fixture(autouse=True, scope="module")
def test_structures():
    return _test_structures


@pytest.fixture(autouse=True, scope="module")
def test_condensed_structures():
    return _test_condensed_structures
