import json
import datetime

import pytest

from monty.io import zopen

from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.electric import ElectricMultipoleDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@pytest.fixture(scope="session")
def test_tasks(test_dir):
    with zopen(test_dir / "multipole_docs.json.gz", "rt") as f:
        data = json.load(f)

    for d in data:
        d["last_updated"] = datetime.datetime.strptime(
            d["last_updated"]["string"], "%Y-%m-%d %H:%M:%S.%f"
        )

    tasks = [TaskDocument(**t) for t in data]
    return tasks


def test_electric_multipole(test_tasks):
    # First, test from SP
    sp_doc = ElectricMultipoleDoc.from_task(
        test_tasks[0], molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )
    assert sp_doc.property_name == "multipole_moments"
    assert sp_doc.total_dipole == pytest.approx(4.2371)
    assert sp_doc.dipole_moment[0] == pytest.approx(-3.2443)
    assert sp_doc.dipole_moment[1] == pytest.approx(-2.4294)
    assert sp_doc.dipole_moment[2] == pytest.approx(-1.2352)
    assert sp_doc.resp_total_dipole == pytest.approx(4.2845)
    assert len(sp_doc.quadrupole_moment) == 6
    assert len(sp_doc.octopole_moment) == 10
    assert len(sp_doc.hexadecapole_moment) == 15
    assert sp_doc.quadrupole_moment["XX"] == pytest.approx(-55.6651)
    assert sp_doc.octopole_moment["XXZ"] == pytest.approx(9.7933)
    assert sp_doc.hexadecapole_moment["YYZZ"] == pytest.approx(-78.2281)

    # Test from force calc
    force_doc = ElectricMultipoleDoc.from_task(
        test_tasks[1], molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )
    assert force_doc.total_dipole == pytest.approx(6.562)
    assert force_doc.dipole_moment[0] == pytest.approx(5.4663)

    # Test from FFOpt
    ffopt_doc = ElectricMultipoleDoc.from_task(
        test_tasks[2], molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )
    assert ffopt_doc.quadrupole_moment["XZ"] == pytest.approx(0.1372)

    # Test from opt
    opt_doc = ElectricMultipoleDoc.from_task(
        test_tasks[3], molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )
    assert opt_doc.octopole_moment["YZZ"] == pytest.approx(35.289)
    assert opt_doc.total_dipole == ffopt_doc.total_dipole

    # Test from freq
    freq_doc = ElectricMultipoleDoc.from_task(
        test_tasks[4], molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2"
    )
    assert freq_doc.hexadecapole_moment["ZZZZ"] == pytest.approx(-366.0089)
