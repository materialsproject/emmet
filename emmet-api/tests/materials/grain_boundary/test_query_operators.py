from emmet.api.routes.materials.grain_boundary.query_operators import (
    GBStructureQuery,
)
from emmet.core.grain_boundary import GBTypeEnum


def test_grain_boundary_structure_query():
    op = GBStructureQuery()

    assert op.query(
        sigma=5,
        type=GBTypeEnum.twist,
        chemsys="Si-Fe",
        pretty_formula="Fe2Si4",
        gb_plane="1,1,1",
        rotation_axis="1,0,1",
    ) == {
        "criteria": {
            "sigma": 5,
            "type": "twist",
            "chemsys": "Fe-Si",
            "pretty_formula": "FeSi2",
            "gb_plane": [1, 1, 1],
            "rotation_axis": [1, 0, 1],
        }
    }
