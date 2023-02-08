import pytest
from monty.serialization import loadfn
from emmet.core.molecules.summary import SummaryDoc


@pytest.fixture(scope="session")
def docs_data(test_dir):
    raw = loadfn(test_dir / "6f98ac0d12632218f92d3a1bc9475d1d-C3H4Li1O3-0-2_new.json")
    return raw


def test_summary_doc(docs_data):
    summary_doc = SummaryDoc.from_docs(molecule_id="6f98ac0d12632218f92d3a1bc9475d1d-C3H4Li1O3-0-2", docs=docs_data)

    assert summary_doc.property_name == "summary"
    assert summary_doc.electronic_energy is not None
    assert summary_doc.total_enthalpy is not None
    assert summary_doc.frequencies is not None
    assert (summary_doc.open_shell["DIELECTRIC=18,500;N=1,415;ALPHA=0,000;BETA=0,735;GAMMA=20,200;PHI=0,000;PSI=0,000"]
            is True)
    assert summary_doc.nbo_population is not None
    assert summary_doc.bonds is not None
    assert summary_doc.electron_affinity is None
