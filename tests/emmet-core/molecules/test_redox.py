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


def test_redox(test_mols):
    entries = list()
    for m in test_mols:
        for e in m.entries:
            entries.append(e)

    redox_docs = RedoxDoc.from_entries(entries)

    assert len(redox_docs) == 17
    assert redox_docs[0].property_name == "redox"

    assert redox_docs[1].electron_affinity == pytest.approx(-2.928377375046328)
    assert str(redox_docs[1].ea_id) == "847651"
    assert redox_docs[1].ionization_energy == pytest.approx(7.115431161042942)
    assert str(redox_docs[1].ie_id) == "891146"