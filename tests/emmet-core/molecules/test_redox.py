import pytest

from monty.serialization import loadfn

from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.redox import RedoxDoc


#TODO: REGENERATE AND FIX


@pytest.fixture(scope="session")
def test_mols(test_dir):
    mols = loadfn((test_dir / "builder_mols_set.json").as_posix())
    mols = [MoleculeDoc(**x) for x in mols]

    return mols


def test_redox(test_mols):
    entries = list()
    for m in test_mols:
        for e in m.entries:
            entries.append(e)

    redox_docs = RedoxDoc.from_entries(entries)

    assert len(redox_docs) == 40
    assert redox_docs[0].property_name == "redox"

    assert redox_docs[1].electron_affinity == pytest.approx(-7.1246847304349075)
    assert redox_docs[1].ionization_energy == pytest.approx(13.396578621769333)