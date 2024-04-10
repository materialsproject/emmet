from emmet.builders.classical_md.utils import create_universe, create_solute
from openff.interchange import Interchange

from emmet.core.classical_md.solvation import SolvationDoc


def test_create_universe(ec_emc_taskdoc, ec_emc_traj):
    interchange = Interchange.parse_raw(ec_emc_taskdoc.interchange)
    mol_specs = ec_emc_taskdoc.molecule_specs

    u = create_universe(
        interchange,
        mol_specs,
        str(ec_emc_traj),
        traj_format="DCD",
    )

    solute = create_solute(u, solute_name="Li", networking_solvents=["PF6"])

    SolvationDoc.from_solute(solute)

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
