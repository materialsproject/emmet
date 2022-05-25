import pytest

from monty.serialization import loadfn

from emmet.core.jaguar.task import TaskDocument
from emmet.core.jaguar.pes import PESMinimumDoc, TransitionStateDoc
from emmet.core.jaguar.reactions import ReactionDoc


@pytest.fixture(scope="session")
def rct(test_dir):
    task = loadfn((test_dir / "jaguar" / "test_reaction_rct_87865.json").as_posix())
    task_doc = TaskDocument(**task)
    return PESMinimumDoc.from_tasks([task_doc])


@pytest.fixture(scope="session")
def pro(test_dir):
    task = loadfn((test_dir / "jaguar" / "test_reaction_pro_87864.json").as_posix())
    task_doc = TaskDocument(**task)
    return PESMinimumDoc.from_tasks([task_doc])


@pytest.fixture(scope="session")
def ts(test_dir):
    task = loadfn((test_dir / "jaguar" / "test_reaction_ts_87861.json").as_posix())
    task_doc = TaskDocument(**task)
    return TransitionStateDoc.from_tasks([task_doc])


def test_reaction(rct, pro, ts):
    rxn = ReactionDoc.from_docs(rct, pro, ts)

    assert str(rxn.reaction_id) == "87864-87861-87865"
    assert rxn.dG_barrier == pytest.approx(0.265, 0.001)
    assert rxn.bond_types_formed_nometal == ["C-O"]
    assert len(rxn.bond_types_broken_nometal) == 0