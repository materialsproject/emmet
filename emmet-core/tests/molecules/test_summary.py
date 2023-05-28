import pytest
from monty.serialization import loadfn
from emmet.core.molecules.summary import MoleculeSummaryDoc


@pytest.fixture(scope="session")
def docs_data(test_dir):
    raw = loadfn(test_dir / "3dfd058d8b422143d386d1ec9a723987-C1Li1O3-m1-1.json.gz")
    return raw


def test_summary_doc(docs_data):
    summary_doc = MoleculeSummaryDoc.from_docs(
        molecule_id="3dfd058d8b422143d386d1ec9a723987-C1Li1O3-m1-1", docs=docs_data
    )

    assert summary_doc.property_name == "summary"
    assert summary_doc.electronic_energy is not None
    assert summary_doc.total_enthalpy is not None
    assert summary_doc.frequencies is not None
    assert summary_doc.nbo_population is None
    assert summary_doc.electron_affinity is None
    assert summary_doc.bonds is not None
    assert summary_doc.binding_data is None
