from emmet.core.io.pymatgen import Ordering, Element, OrbitalType

from emmet.api.routes.materials.electronic_structure.query_operators import (
    BSDataQuery,
    DOSDataQuery,
    ESSummaryDataQuery,
)
from emmet.core.band_theory import BSPathType
from emmet.core.electronic_structure import DOSProjectionType


def test_es_summary_query():
    op = ESSummaryDataQuery()

    assert op.query(
        magnetic_ordering=Ordering.FiM, is_gap_direct=True, is_metal=False
    ) == {
        "criteria": {
            "magnetic_ordering": "FiM",
            "is_gap_direct": True,
            "is_metal": False,
        }
    }


def test_bs_data_query():
    op = BSDataQuery()

    q = op.query(
        path_type=BSPathType.setyawan_curtarolo,
        band_gap_min=0,
        band_gap_max=5,
        efermi_min=0,
        efermi_max=5,
        magnetic_ordering=Ordering.FM,
        is_gap_direct=True,
        is_metal=False,
    )

    fields = [
        "bandstructure.setyawan_curtarolo.band_gap",
        "bandstructure.setyawan_curtarolo.efermi",
    ]

    c = {field: {"$gte": 0, "$lte": 5} for field in fields}

    assert q == {
        "criteria": {
            "bandstructure.setyawan_curtarolo.magnetic_ordering": "FM",
            "bandstructure.setyawan_curtarolo.is_gap_direct": True,
            "bandstructure.setyawan_curtarolo.is_metal": False,
            **c,
        }
    }


def test_dos_data_query():
    op = DOSDataQuery()

    proj_types = [
        DOSProjectionType.total,
        DOSProjectionType.elemental,
        DOSProjectionType.orbital,
    ]

    for proj_type in proj_types:
        q = op.query(
            projection_type=proj_type,
            spin="1",
            element=Element.Si if proj_type != DOSProjectionType.total else None,
            orbital=OrbitalType.s if proj_type != DOSProjectionType.total else None,
            band_gap_min=0,
            band_gap_max=5,
            efermi_min=0,
            efermi_max=5,
            magnetic_ordering=Ordering.FM,
        )

        if proj_type == DOSProjectionType.total:
            fields = [
                "dos.total.1.band_gap",
                "dos.total.1.efermi",
            ]
        elif proj_type == DOSProjectionType.elemental:
            fields = [
                "dos.elemental.Si.s.1.band_gap",
                "dos.elemental.Si.s.1.efermi",
            ]

        elif proj_type == DOSProjectionType.orbital:
            fields = [
                "dos.orbital.s.1.band_gap",
                "dos.orbital.s.1.efermi",
            ]

        c = {field: {"$gte": 0, "$lte": 5} for field in fields}

        assert q == {"criteria": {"dos.magnetic_ordering": "FM", **c}}
