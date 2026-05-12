from emmet.core.io.pymatgen import Element

from emmet.api.routes.materials.xas.query_operators import XASIDQuery, XASQuery
from emmet.core.xas import XasEdge, XasType


def test_xas_operator():
    op = XASQuery()

    assert op.query(
        edge=XasEdge.K, spectrum_type=XasType.XANES, absorbing_element=Element("Cu")
    ) == {
        "criteria": {"edge": "K", "absorbing_element": "Cu", "spectrum_type": "XANES"}
    }


def test_xas_single_id():
    op = XASIDQuery()

    assert op.query(spectrum_ids="mp-149-XANES-Pd-K") == {
        "criteria": {
            "task_id": {"$in": ["aaaaaaft"]},
            "spectrum_type": {"$in": ["XANES"]},
            "absorbing_element": {"$in": ["Pd"]},
            "edge": {"$in": ["K"]},
        }
    }


def test_xas_multi_id():
    op = XASIDQuery()

    assert op.query(
        spectrum_ids="mp-149-XANES-Pd-K, mp-8951-XANES-Pd-K, mp-bmm-XANES-Pd-K"
    ) == {
        "criteria": {
            "task_id": {
                "$in": [
                    "aaaaaaft",
                    "aaaaabmm",
                    "aaaaangh",
                ]
            },
            "spectrum_type": {"$in": ["XANES"]},
            "absorbing_element": {"$in": ["Pd"]},
            "edge": {"$in": ["K"]},
        }
    }
