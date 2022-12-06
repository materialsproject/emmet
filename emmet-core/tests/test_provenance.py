from datetime import datetime
from monty.dev import deprecated

import pytest
from pymatgen.core import Lattice, Structure
from pymatgen.util.provenance import Author, HistoryNode, StructureNL

from emmet.core.provenance import Database, ProvenanceDoc, SNLDict


@pytest.fixture
def structure():
    test_latt = Lattice.cubic(3.0)
    test_struc = Structure(lattice=test_latt, species=["Fe"], coords=[[0, 0, 0]])
    return test_struc


@pytest.fixture
def snls(structure):

    docs = [
        StructureNL(
            structure,
            authors=[Author("test{i}", "test@test.com").as_dict()],
            history=[HistoryNode("nothing", "url.com", {})],
            created_at=datetime.utcnow(),
            references="",
        ).as_dict()
        for i in range(3)
    ]
    docs[0]["snl_id"] = "icsd-2"
    docs[1]["snl_id"] = "user-1"
    docs[2]["snl_id"] = "pf-3"

    return [SNLDict(**d) for d in docs]


def test_from_snls(snls, structure):

    doc = ProvenanceDoc.from_SNLs(
        material_id="mp-3", structure=structure, snls=snls, deprecated=False
    )

    assert isinstance(doc, ProvenanceDoc)
    assert doc.property_name == "provenance"
    assert doc.material_id == "mp-3"
    assert doc.theoretical is True
    assert doc.database_IDs == {
        Database.ICSD: ["icsd-2"],
        Database.Pauling_Files: ["pf-3"],
    }

    # Test experimental detection
    snls[0].about.history[0].description["experimental"] = True
    assert (
        ProvenanceDoc.from_SNLs(
            material_id="mp-3", snls=snls, structure=structure, deprecated=False
        ).theoretical
        is False
    )
    assert doc.dict(exclude_none=True)["property_name"] == "provenance"
