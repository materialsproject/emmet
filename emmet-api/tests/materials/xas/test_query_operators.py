from emmet.api.routes.materials.xas.query_operators import XASQuery, XASIDQuery

from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn

from emmet.core.xas import Edge, Type
from pymatgen.core.periodic_table import Element


def test_xas_operator():
    op = XASQuery()

    assert op.query(
        edge=Edge.K, spectrum_type=Type.XANES, absorbing_element=Element("Cu")
    ) == {
        "criteria": {"edge": "K", "absorbing_element": "Cu", "spectrum_type": "XANES"}
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")

        assert new_op.query(
            edge=Edge.K, spectrum_type=Type.XANES, absorbing_element=Element("Cu")
        ) == {
            "criteria": {
                "edge": "K",
                "absorbing_element": "Cu",
                "spectrum_type": "XANES",
            }
        }


def test_xas_task_id_operator():
    op = XASIDQuery()

    assert op.query(spectrum_ids="mp-149-XANES-Pd-K, mp-8951-XANES-Pd-K") == {
        "criteria": {
            "spectrum_id": {"$in": ["mp-149-XANES-Pd-K", "mp-8951-XANES-Pd-K"]}
        }
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")

        assert new_op.query(spectrum_ids="mp-149-XANES-Pd-K, mp-8951-XANES-Pd-K") == {
            "criteria": {
                "spectrum_id": {"$in": ["mp-149-XANES-Pd-K", "mp-8951-XANES-Pd-K"]}
            }
        }
