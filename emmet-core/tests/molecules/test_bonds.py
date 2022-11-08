import json
import datetime
import copy

import pytest

from monty.io import zopen
from monty.serialization import loadfn

from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.bonds import BondingDoc


@pytest.fixture(scope="session")
def test_tasks(test_dir):
    with zopen(test_dir / "liec_tasks.json.gz") as f:
        data = json.load(f)

    for d in data:
        d["last_updated"] = datetime.datetime.strptime(
            d["last_updated"]["string"], "%Y-%m-%d %H:%M:%S.%f"
        )

    tasks = [TaskDocument(**t) for t in data]
    return tasks


@pytest.fixture(scope="session")
def nbo_task(test_dir):
    return TaskDocument(**loadfn(test_dir / "open_shell_nbo_task.json.gz"))

@pytest.mark.skip(reason="Waiting on molecule update.")
def test_bonding(test_tasks, nbo_task):
    # No Critic2 or NBO
    ob_mee = BondingDoc.from_task(
        test_tasks[0],
        molecule_id="libe-115880",
        preferred_methods=["OpenBabelNN + metal_edge_extender"],
    )
    assert ob_mee.property_name == "bonding"
    assert ob_mee.method == "OpenBabelNN + metal_edge_extender"
    assert len(ob_mee.bonds) == 12
    assert len(ob_mee.bonds_nometal) == 10
    assert set(ob_mee.bond_types.keys()) == {"C-C", "C-H", "C-O", "Li-O"}

    ob_critic = BondingDoc.from_task(
        test_tasks[3], molecule_id="libe-115880", preferred_methods=["critic2"]
    )
    assert ob_critic.method == "critic2"
    assert len(ob_critic.bonds) == 12
    assert len(ob_critic.bonds_nometal) == 10
    assert set(ob_critic.bond_types.keys()) == {"C-C", "C-H", "C-O", "Li-O"}

    assert ob_mee.molecule_graph.isomorphic_to(ob_critic.molecule_graph)

    nbo = BondingDoc.from_task(
        nbo_task, molecule_id="libe-115880", preferred_methods=["nbo"]
    )
    assert nbo.method == "nbo"
    assert len(nbo.bonds) == 9
    assert len(nbo.bonds_nometal) == 9
    assert set(nbo.bond_types.keys()) == {"C-H", "C-O"}
