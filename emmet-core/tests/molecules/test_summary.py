import pytest
from monty.serialization import loadfn
from emmet.core.molecules.summary import SummaryDoc


@pytest.fixture(scope="session")
def docs_data(test_dir):
    raw = loadfn(test_dir / "e793adf5298c07bc8a4f0f2c4db8da01-C2H4-m2-1.json.gz")
    return raw


def test_summary_doc(docs_data):
    summary_doc = SummaryDoc.from_docs(molecule_id="e793adf5298c07bc8a4f0f2c4db8da01-C2H4-m2-1", docs=docs_data)

    assert summary_doc.property_name == "summary"
    assert summary_doc.electronic_energy is not None
    assert summary_doc.total_enthalpy is not None
    assert summary_doc.frequencies is not None
    assert summary_doc.nbo_population is not None
    assert summary_doc.electron_affinity is not None
    assert summary_doc.bonds is not None
