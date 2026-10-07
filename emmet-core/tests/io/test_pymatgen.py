"""Test that pymatgen-related imports work."""

import pytest
from emmet.core.io.pymatgen import (
    _class_map,
    __dir__ as pmg_io_dir,
)


def test_dir():
    import emmet.core.io.pymatgen as pmg_io_layer

    pmg_list_dir = pmg_io_dir()
    assert pmg_list_dir == sorted(pmg_list_dir)
    assert all(isinstance(v, str) for v in pmg_list_dir)
    assert set(_class_map) <= set(pmg_list_dir)
    assert dir(pmg_io_layer) == pmg_list_dir
    # dir() protocol: every listed name must be a valid attribute name
    assert not any("." in name for name in pmg_list_dir)


def test_bad_import():
    with pytest.raises(ImportError, match="cannot import name"):
        from emmet.core.io.pymatgen import foobar  # noqa: F401


@pytest.mark.parametrize("object_name", sorted(_class_map))
def test_imports(object_name: str):
    """Test that all imports defined in the I/O layer work."""
    import emmet.core.io.pymatgen as pmg_io_layer

    try:
        getattr(pmg_io_layer, object_name)
    except (ImportError, AttributeError) as exc:
        import_str = ".".join(["pymatgen", object_name, _class_map[object_name]])
        pytest.fail(f"Import of {import_str!r} failed with exception {exc}")
