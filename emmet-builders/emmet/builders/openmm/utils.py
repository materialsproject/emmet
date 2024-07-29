import warnings
from typing import Optional, Union
from pathlib import Path

import numpy as np
from MDAnalysis import Universe
from solvation_analysis.solute import Solute

from openff.interchange import Interchange
import openff.toolkit as tk

from maggma.core import Store

from emmet.core.openff import MoleculeSpec
from emmet.core.openmm import OpenMMTaskDocument


def create_universe(
    interchange: Interchange,
    mol_specs: Optional[list[MoleculeSpec]],
    traj_file: Union[Path, str],
    traj_format=None,
):
    """
    Create a Universe object from an Interchange object and a trajectory file.

    Parameters
    ----------
    interchange : Interchange
        The Interchange object containing the topology and parameters.
    mol_specs : list[MoleculeSpec] or None
        A list of MoleculeSpec objects or None.
    traj_file : Path or str
        The path to the trajectory file.
    traj_format : str, optional
        The format of the trajectory file.

    Returns
    -------
    Universe
        The created Universe object.
    """
    # TODO: profile this
    topology = interchange.to_openmm_topology()

    u = Universe(
        topology,
        str(traj_file),
        format=traj_format,
    )

    # TODO: this won't work
    mols = [mol for mol in interchange.topology.molecules]

    label_types(u, mols)
    label_resnames(u, mols, mol_specs)
    label_charges(u, mols, mol_specs)

    return u


def label_types(u: Universe, mols: list[tk.Molecule]):
    """
    Label atoms in the Universe with unique types based on the molecules.

    Parameters
    ----------
    u : Universe
        The Universe object to label.
    mols : list[tk.Molecule]
        The list of Molecule objects.
    """
    # add unique counts for each
    offset = 0
    mol_types = {}
    for mol in set(mols):
        mol_types[mol] = range(offset, offset + mol.n_atoms)
        offset += mol.n_atoms
    all_types = np.concatenate([mol_types[mol] for mol in mols])
    u.add_TopologyAttr("types", all_types)


def label_resnames(
    u: Universe, mols: list[tk.Molecule], mol_specs: Optional[list[MoleculeSpec]]
):
    """
    Label atoms in the Universe with residue names.

    Parameters
    ----------
    u : Universe
        The Universe object to label.
    mols : list[tk.Molecule]
        The list of Molecule objects.
    mol_specs : list[MoleculeSpec] or None
        A list of MoleculeSpec objects or None.
    """
    if mol_specs:
        resname_list = [[spec.name] * spec.count for spec in mol_specs]
        resnames = np.concatenate(resname_list)
    else:
        resname_list = [mol.to_smiles() for mol in mols]
        resnames = np.array(resname_list)
    u.add_TopologyAttr("resnames", resnames)


def label_charges(
    u: Universe, mols: list[tk.Molecule], mol_specs: Optional[list[MoleculeSpec]]
):
    """
    Label atoms in the Universe with partial charges.

    Parameters
    ----------
    u : Universe
        The Universe object to label.
    mols : list[tk.Molecule]
        The list of Molecule objects.
    mol_specs : list[MoleculeSpec]
        A list of MoleculeSpec objects.
    """
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


def create_solute(
    u: Universe,
    solute_name: str,
    networking_solvents: Optional[list[str]] = None,
    fallback_radius: Optional[float] = None,
    include_solute_in_solvents=False,
    analysis_classes=["coordination", "pairing", "speciation", "networking"],
    step=1,
):
    """
    Create a Solute object from a Universe object.

    Parameters
    ----------
    u : Universe
        The Universe object containing the solute and solvent atoms.
    solute_name : str
        The residue name of the solute.
    networking_solvents : list[str] or None, optional
        A list of residue names of networking solvents or None.
    fallback_radius : float or None, optional
        The fallback radius for kernel calculations or None.
    include_solute_in_solvents : bool, optional
        Whether to include the solute in the solvents dictionary. Default is False.
    analysis_classes : list[str], optional
        The analysis classes to run. Default is ("coordination", "pairing", "speciation", "networking").
    step : int, optional
        The step size for the analysis. Default is 1.

    Returns
    -------
    Solute
        The created Solute object.
    """
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
    """
    Identify the solute in a Universe object.

    Currently just finds the name of a sinlge cation based on the
    partial charges in the universe.

    Parameters
    ----------
    u : Universe
        The Universe object

    Returns
    -------
    str
        The residue name of the solute.
    """
    cation_residues = u.residues[u.residues.charges > 0.01]
    unique_names = np.unique(cation_residues.resnames)
    if len(unique_names) > 1:
        # TODO: fail gracefully?
        raise ValueError("Multiple cationic species detected, not yet supported.")
    return unique_names[0]


def identify_networking_solvents(u: Universe):
    """
    Identify the networking solvents in a Universe object.

    Currently just finds the name of all anions based on the
    partial charges in the universe.

    Parameters
    ----------
    u : Universe
        The Universe object

    Returns
    -------
    list[str]
        The residue names of the networking solvents.
    """
    # currently just anions
    anion_residues = u.residues[u.residues.charges < -0.01]
    unique_names = np.unique(anion_residues.resnames)
    return list(unique_names)


def insert_blobs(blobs_store: Store, task_doc: dict, include_traj: bool = True):
    """Insert blobs into a task document."""
    interchange_uuid = task_doc["interchange"]["blob_uuid"]
    interchange_blob = blobs_store.query_one({"blob_uuid": interchange_uuid})
    task_doc["interchange"] = interchange_blob["data"]

    if len(task_doc["calcs_reversed"]) == 0:
        raise ValueError("No calculations found in job output.")

    for calc in task_doc["calcs_reversed"]:
        if not include_traj:
            calc["output"]["traj_blob"] = None

        traj_blob = calc["output"]["traj_blob"]

        if traj_blob:
            traj_uuid = calc["output"]["traj_blob"]["blob_uuid"]
            traj_blob = blobs_store.query_one({"blob_uuid": traj_uuid})
            calc["output"]["traj_blob"] = traj_blob["data"]


def instantiate_universe(
    md_docs: Store,
    blobs: Store,
    job_uuid: str,
    traj_directory: Union[str, Path] = ".",
    overwrite_local_traj: bool = True,
):
    """
    Instantiate a MDAnalysis universe from a task document.

    This is useful if you want to analyze a small number of systems
    without running the whole build pipeline.

    Args:
        md_docs: Store
            The store containing the task documents.
        blobs: Store
            The store containing the blobs.
        job_uuid: str
            The UUID of the job.
        traj_directory: str
            Name of the DCD file to write.
        overwrite_local_traj: bool
            Whether to overwrite the local trajectory if it exists.
    """

    # pull job
    docs = list(md_docs.query(criteria={"uuid": job_uuid}))
    if len(docs) != 1:
        raise ValueError(
            f"The job_uuid, {job_uuid}, must be unique. Found {len(docs)} documents."
        )
    task_doc = docs[0]["output"]
    traj_file_type = task_doc["calcs_reversed"][0]["input"]["traj_file_type"]

    # define path to trajectory
    traj_directory = Path(traj_directory)
    traj_directory.mkdir(parents=True, exist_ok=True)
    traj_path = traj_directory / f"{job_uuid}.{traj_file_type}"

    # download and insert blobs if necessary
    new_traj = not traj_path.exists() or overwrite_local_traj
    insert_blobs(blobs, task_doc, include_traj=new_traj)
    task_doc = OpenMMTaskDocument.parse_obj(task_doc)
    if new_traj:
        with open(traj_path, "wb") as f:
            f.write(task_doc.calcs_reversed[0].output.traj_blob)

    # create interchange
    interchange_str = task_doc.interchange.decode("utf-8")
    interchange = Interchange.parse_raw(interchange_str)

    return create_universe(
        interchange,
        task_doc.molecule_specs,
        traj_path,
        traj_format=traj_file_type,
    )
