import pytest

from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.orbitals import OrbitalDoc

from tests.conftest_qchem import safe_load


@pytest.fixture(scope="session")
def closed_shell(test_dir):
    task = TaskDocument(**safe_load((test_dir / "closed_shell_nbo_task.json.gz")))
    return task


@pytest.fixture(scope="session")
def open_shell(test_dir):
    task = TaskDocument(**safe_load((test_dir / "open_shell_nbo_task.json.gz")))
    return task


@pytest.fixture(scope="session")
def new_closed(test_dir):
    task = TaskDocument(**safe_load((test_dir / "closed_shell_with3c.json.gz")))
    return task


@pytest.fixture(scope="session")
def new_open(test_dir):
    task = TaskDocument(**safe_load((test_dir / "open_shell_with3c.json.gz")))
    return task


def test_orbital(closed_shell, open_shell):
    # Test closed-shell NBO parsing
    doc = OrbitalDoc.from_task(
        closed_shell, "b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2", deprecated=False
    )

    assert doc.property_name == "natural bonding orbitals"
    assert doc.open_shell is False

    assert len(doc.nbo_population) == len(closed_shell.output.initial_molecule)
    assert doc.nbo_population[0].valence_electrons == pytest.approx(2.75426)
    assert len(doc.nbo_lone_pairs) == 3
    assert doc.nbo_lone_pairs[0].s_character == pytest.approx(0.02)
    assert doc.nbo_lone_pairs[0].atom_index == 0
    assert len(doc.nbo_bonds) == 10
    assert doc.nbo_bonds[0].atom1_s_character == pytest.approx(29.93)
    assert doc.nbo_bonds[0].atom1_index == 0
    assert doc.nbo_bonds[0].atom2_index == 3
    assert len(doc.nbo_interactions) == 95
    assert doc.nbo_interactions[0].donor_index == 8
    assert doc.nbo_interactions[0].acceptor_index == 19
    assert doc.nbo_interactions[0].energy_difference == pytest.approx(0.95)
    assert doc.alpha_population is None
    assert doc.beta_population is None

    # Test open-shell NBO parsing
    doc = OrbitalDoc.from_task(
        open_shell, "b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2", deprecated=False
    )

    assert doc.open_shell is True

    assert len(doc.nbo_population) == len(open_shell.output.initial_molecule)
    assert doc.alpha_population is not None
    assert doc.beta_population is not None
    assert doc.nbo_lone_pairs is None
    assert doc.nbo_bonds is None


def test_new_parser(new_closed, new_open):
    # Test closed-shell parsing including 3-center bonds and hyperbonds
    cs_doc = OrbitalDoc.from_task(
        new_closed, "b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2", deprecated=False
    )

    assert cs_doc.open_shell is False
    assert len(cs_doc.nbo_three_center_bonds) == 3
    assert cs_doc.nbo_three_center_bonds[1].atom1_polarization == pytest.approx(34.47)
    assert cs_doc.nbo_hyperbonds[2].hybrid_index_2 == 184

    # Test open-shell parsing including 3-center bonds and hyperbonds
    os_doc = OrbitalDoc.from_task(
        new_open, "b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2", deprecated=False
    )

    assert os_doc.open_shell is True
    assert len(os_doc.alpha_three_center_bonds) == 3
    assert os_doc.alpha_three_center_bonds[0].atom3_index == 14
    assert len(os_doc.beta_hyperbonds) == 2
    assert os_doc.beta_hyperbonds[0].fraction_12 == pytest.approx(41.2)
