from emmet.builders.classical_md.utils import create_universe
from openff.interchange import Interchange


def test_create_universe(ec_emc_taskdoc, ec_emc_traj):
    interchange = Interchange.parse_raw(ec_emc_taskdoc.interchange)
    mol_specs = ec_emc_taskdoc.molecule_specs

    u = create_universe(
        interchange,
        mol_specs,
        str(ec_emc_traj),
        traj_format="DCD",
    )

    return


def test_label_types():
    return


def test_label_resnames():
    return


def test_label_charges():
    return


def test_create_solute():
    return


def test_length_not_reduced():
    return
