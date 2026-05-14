"""Test that pymatgen-related imports work."""

import pytest
from emmet.core.io.pymatgen import (
    _class_map,
    __dir__ as pmg_io_dir,
    _name_collision_aliases,
)


def test_dir():
    pmg_list_dir = pmg_io_dir()
    assert pmg_list_dir == sorted(
        ".".join(["pymatgen", base_import, _name_collision_aliases.get(name, name)])
        for name, base_import in _class_map.items()
    )
    assert all(isinstance(v, str) for v in pmg_list_dir)


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
