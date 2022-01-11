import json
import datetime
import copy
import pickle

import pytest

from monty.io import zopen
from monty.serialization import loadfn

from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.redox import RedoxDoc


@pytest.fixture(scope="session")
def test_mols(test_dir):
    with open((test_dir / "redox_mol_docs.pickle").as_posix(), "rb") as f:
        data = pickle.load(f)

    return data


def test_redox(test_mols):
    entries = list()
    for m in test_mols:
        for e in m.entries:
            entries.append(e)

    redox_docs = RedoxDoc.from_entries(entries)

    assert len(redox_docs) == 3
    assert redox_docs[0].property_name == "redox"

    assert redox_docs[1].electron_affinity == pytest.approx(-0.7226193632551298)
    assert redox_docs[1].ea_id == 845318
    assert redox_docs[1].ionization_energy == pytest.approx(11.058520187149718)
    assert redox_docs[1].ie_id == 888790
    assert redox_docs[1].reduction_free_energy == pytest.approx(-1.0584641522518723)
    assert redox_docs[1].red_id == 116015
    assert redox_docs[1].oxidation_free_energy == pytest.approx(11.049545505758942)
    assert redox_docs[1].ox_id == 116016