from emmet.builders.classical_md.utils import (
    create_universe,
    create_solute,
    label_types,
    label_resnames,
    label_charges,
)
from openff.interchange import Interchange
from openff.units import unit
import openff.toolkit as tk
from emmet.core.classical_md.solvation import SolvationDoc
from emmet.core.classical_md import MoleculeSpec
from MDAnalysis import Universe
import numpy as np


def test_create_universe_and_solute(ec_emc_taskdoc, ec_emc_traj):
    interchange = Interchange.parse_raw(ec_emc_taskdoc.interchange)
    mol_specs = ec_emc_taskdoc.molecule_specs

    u = create_universe(
        interchange,
        mol_specs,
        str(ec_emc_traj),
        traj_format="DCD",
    )

    solute = create_solute(u, solute_name="Li", networking_solvents=["PF6"])

    solvation_doc = SolvationDoc.from_solute(solute)

    assert isinstance(u, Universe)
    assert solvation_doc is not None


def test_label_types():
    mols = [tk.Molecule.from_smiles("CCO"), tk.Molecule.from_smiles("OCC")]
    u = Universe.empty(n_atoms=18, trajectory=True)
    label_types(u, mols)

    types = u.atoms.types
    assert len(types) == 18
    assert all(isinstance(t, int) for t in types)


def test_label_resnames():
    mols = [
        tk.Molecule.from_smiles("CCO"),
    ]
    mol_specs = [
        MoleculeSpec(
            name="ethanol",
            count=1,
            openff_mol=mols[0].to_json(),
            charge_scaling=1.0,
            charge_method="null",
        ),
    ]
    u = Universe.empty(n_atoms=9, trajectory=True)
    label_resnames(u, mols, mol_specs)

    resnames = u.atoms.resnames
    assert len(resnames) == 9
    assert "ethanol" in resnames


def test_label_charges():
    mols = [tk.Molecule.from_smiles("O")]
    mols[0].partial_charges = np.array([-0.3, 0.1, 0.2]) * unit.elementary_charge
    mol_specs = [
        MoleculeSpec(
            name="water",
            count=1,
            openff_mol=mols[0].to_json(),
            charge_scaling=1.0,
            charge_method="null",
        ),
    ]
    u = Universe.empty(n_atoms=3, trajectory=True)
    label_charges(u, mols, mol_specs)

    charges = u.atoms.charges
    assert len(charges) == 3
    assert np.isclose(charges[0], -0.3)
    assert np.isclose(charges[2], 0.2)
