import pytest
from monty.serialization import loadfn
from emmet.core.molecules.summary import MoleculeSummaryDoc


@pytest.fixture(scope="session")
def docs_data(test_dir):
    raw = loadfn(test_dir / "3dfd058d8b422143d386d1ec9a723987-C1Li1O3-m1-1.json.gz")
    return raw


def test_summary_doc(docs_data):
    # Reformatting because summary build process changed
    actual_docs = dict()
    for k, v in docs_data.items():
        if k == "molecules":
            actual_docs[k] = v
        else:
            actual_docs[k] = v[0]

    summary_doc = MoleculeSummaryDoc.from_docs(
        molecule_id="3dfd058d8b422143d386d1ec9a723987-C1Li1O3-m1-1", docs=actual_docs
    )

    assert summary_doc.property_name == "summary"
    assert len(summary_doc.bonding) > 0
    assert len(summary_doc.thermo) > 0
    assert len(summary_doc.vibration) > 0
    assert len(summary_doc.redox) > 0
    assert len(summary_doc.orbitals) == 0
    assert len(summary_doc.metal_binding) == 0
