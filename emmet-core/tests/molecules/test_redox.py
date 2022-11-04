import json
import datetime
import copy
import pickle

import pytest

from monty.io import zopen
from monty.serialization import loadfn

from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.redox import RedoxDoc


@pytest.fixture(scope="session")
def test_mols(test_dir):
    mols = loadfn((test_dir / "builder_mols_set.json").as_posix())
    mols = [MoleculeDoc(**x) for x in mols]

    return mols


@pytest.mark.skip(reason="Waiting on molecule update.")
def test_redox(test_mols):
    entries = list()
    for m in test_mols:
        for e in m.entries:
            entries.append(e)

    redox_docs = RedoxDoc.from_entries(entries)

    assert len(redox_docs) == 18
    assert redox_docs[0].property_name == "redox"

    assert redox_docs[1].electron_affinity == pytest.approx(-1.888795786559726)
    assert str(redox_docs[1].ea_id) == "116081"
    assert redox_docs[1].ionization_energy == pytest.approx(2.392317962137756)
    assert str(redox_docs[1].ie_id) == "116001"
