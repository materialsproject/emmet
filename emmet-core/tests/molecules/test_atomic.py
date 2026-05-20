from emmet.core.molecules.atomic import PartialChargesDoc, PartialSpinsDoc

from tests.conftest_qchem import OPENBABEL_INSTALLED


def test_partial_charges(liec_tasks):
    # Test RESP
    pcd = PartialChargesDoc.from_task(
        liec_tasks[0],
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["resp"],
    )

    assert pcd.property_name == "partial_charges"
    assert pcd.method == "resp"
    assert pcd.partial_charges == liec_tasks[0].output.resp

    # Test Mulliken
    pcd = PartialChargesDoc.from_task(
        liec_tasks[0],
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["mulliken"],
    )

    assert pcd.method == "mulliken"
    assert pcd.partial_charges == liec_tasks[0].output.mulliken

    # Test Critic2
    pcd = PartialChargesDoc.from_task(
        liec_tasks[3],
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["critic2"],
    )

    assert pcd.method == "critic2"
    assert pcd.partial_charges == liec_tasks[3].critic2["processed"]["charges"]

    # Test NBO
    pcd = PartialChargesDoc.from_task(
        liec_tasks[4],
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["nbo"],
    )

    assert pcd.method == "nbo"
    nbo_charges = [
        float(liec_tasks[4].output.nbo["natural_populations"][0]["Charge"][str(i)])
        for i in range(11)
    ]
    assert pcd.partial_charges == nbo_charges


def test_partial_spins(open_shell_nbo_task):
    # Test Mulliken
    psd = PartialSpinsDoc.from_task(
        open_shell_nbo_task,
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["mulliken"],
    )

    assert psd.property_name == "partial_spins"
    assert psd.method == "mulliken"
    assert psd.partial_spins == [m[1] for m in open_shell_nbo_task.output.mulliken]

    # Test NBO
    psd = PartialSpinsDoc.from_task(
        open_shell_nbo_task,
        molecule_id="b9ba54febc77d2a9177accf4605767db-C1Li2O3-1-2",
        preferred_methods=["nbo"],
    )

    assert psd.method == "nbo"
    spins = [
        float(
            open_shell_nbo_task.output.nbo["natural_populations"][0]["Density"][str(i)]
        )
        for i in range(11)
    ]
    assert psd.partial_spins == spins

    if OPENBABEL_INSTALLED:
        # Sanity check - do properties have hashes
        assert psd.species_hash is not None
