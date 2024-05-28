import warnings

import numpy as np

from openff.interchange import Interchange
import openff.toolkit as tk
from emmet.core.classical_md import MoleculeSpec
from MDAnalysis import Universe
from solvation_analysis.solute import Solute

from pathlib import Path


def create_universe(
    interchange: Interchange,
    mol_specs: list[MoleculeSpec] | None,
    traj_file: Path | str,
    traj_format=None,
):
    # TODO: profile this
    topology = interchange.to_openmm_topology()

    u = Universe(topology, str(traj_file), format=traj_format)

    mols = [mol for mol in interchange.topology.molecules]

    label_types(u, mols)

    label_resnames(u, mols, mol_specs)

    label_charges(u, mols, mol_specs)

    return u


def label_types(u: Universe, mols: list[tk.Molecule]):
    # add unique counts for each
    offset = 0
    mol_types = {}
    for mol in set(mols):
        mol_types[mol] = range(offset, offset + mol.n_atoms)
        offset += mol.n_atoms
    all_types = np.concatenate([mol_types[mol] for mol in mols])
    u.add_TopologyAttr("types", all_types)


def label_resnames(
    u: Universe, mols: list[tk.Molecule], mol_specs: list[MoleculeSpec] | None
):
    if mol_specs:
        resname_list = [[spec.name] * spec.count for spec in mol_specs]
        resnames = np.concatenate(resname_list)
    else:
        resname_list = [mol.to_smiles() for mol in mols]
        resnames = np.array(resname_list)
    u.add_TopologyAttr("resnames", resnames)


def label_charges(u: Universe, mols: list[tk.Molecule], mol_specs: list[MoleculeSpec]):
    charge_arrays = []
    if mol_specs:
        for spec in mol_specs:
            mol = tk.Molecule.from_json(spec.openff_mol)
            charge_arr = np.tile(mol.partial_charges / spec.charge_scaling, spec.count)
            charge_arrays.append(charge_arr)
    else:
        warnings.warn(
            "`mol_specs` are not present so charges cannot be unscaled. "
            "If charges were scaled, conductivity calculations will be inaccurate."
        )
        for mol in mols:
            charge_arrays.append(mol.partial_charges)
    charges = np.concatenate(charge_arrays).magnitude
    u.add_TopologyAttr("charges", charges)


def mol_specs_from_interchange(interchange: Interchange) -> list[MoleculeSpec]:
    return


def create_solute(
    u: Universe,
    solute_name: str,
    networking_solvents: list[str] | None = None,
    fallback_radius: float | None = None,
    include_solute_in_solvents=False,
    analysis_classes="all",
    step=1,
):
    solute = u.select_atoms(f"resname {solute_name}")

    unique_resnames = np.unique(u.atoms.residues.resnames)
    solvents = {
        resname: u.select_atoms(f"resname {resname}") for resname in unique_resnames
    }
    if not include_solute_in_solvents:
        solvents.pop(solute_name, None)

    solute = Solute.from_atoms(
        solute,
        solvents,
        solute_name=solute_name,
        analysis_classes=analysis_classes,
        networking_solvents=networking_solvents,
        kernel_kwargs={"default": fallback_radius},
    )
    solute.run(step=step)
    return solute


def identify_solute(u: Universe):
    # currently just cations
    cation_residues = u.residues[u.residues.charges > 0.01]
    unique_names = np.unique(cation_residues.resnames)
    if len(unique_names) > 1:
        # TODO: fail gracefully?
        raise ValueError("Multiple cationic species detected, not yet supported.")
    return unique_names[0]


def identify_networking_solvents(u: Universe):
    # currently just anions
    anion_residues = u.residues[u.residues.charges < -0.01]
    unique_names = np.unique(anion_residues.resnames)
    return list(unique_names)
