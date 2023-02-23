import pytest
from monty.serialization import loadfn
from emmet.core.molecules.summary import SummaryDoc


@pytest.fixture(scope="session")
def docs_data(test_dir):
    raw = loadfn(test_dir / "35883c6709ca5ee9d065d088bae2cd4e-C3H4Li1O3-0-2.json")
    return raw


def test_summary_doc(docs_data):
    summary_doc = SummaryDoc.from_docs(molecule_id="35883c6709ca5ee9d065d088bae2cd4e-C3H4Li1O3-0-2", docs=docs_data)

    assert summary_doc.property_name == "summary"
    assert summary_doc.electronic_energy is not None
    assert summary_doc.total_enthalpy is not None
    assert summary_doc.frequencies is not None
    assert summary_doc.nbo_population is None
    assert summary_doc.electron_affinity is None
    assert summary_doc.bonds is not None
