from pymatgen.core.periodic_table import Element

from emmet.api.routes.materials.xas.query_operators import XASIDQuery, XASQuery
from emmet.core.xas import XasEdge, XasType


def test_xas_operator():
    op = XASQuery()

    assert op.query(
        edge=XasEdge.K, spectrum_type=XasType.XANES, absorbing_element=Element("Cu")
    ) == {
        "criteria": {"edge": "K", "absorbing_element": "Cu", "spectrum_type": "XANES"}
    }


def test_xas_task_id_operator():
    op = XASIDQuery()

    assert op.query(spectrum_ids="mp-149-XANES-Pd-K, mp-8951-XANES-Pd-K") == {
        "pipeline": [
            {
                "$match": {
                    "spectrum_id.identifier": {"$in": ["mp-aaaaaaft", "mp-aaaaangh"]},
                    "spectrum_id.suffix": "XANES-Pd-K",
                }
            },
            {
                "$addFields": {
                    "_idcat": {
                        "$concat": [
                            "$spectrum_id.identifier",
                            "-",
                            "$spectrum_id.suffix",
                        ]
                    }
                }
            },
            {
                "$match": {
                    "_idcat": {
                        "$in": ["mp-aaaaaaft-XANES-Pd-K", "mp-aaaaangh-XANES-Pd-K"]
                    }
                }
            },
            {"$unset": "_idcat"},
        ]
    }
