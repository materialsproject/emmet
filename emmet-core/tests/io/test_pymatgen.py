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
