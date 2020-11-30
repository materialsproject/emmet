from __future__ import annotations

from typing import Union

from monty.json import MSONable
from pymatgen import Molecule
from pymatgen.analysis.graphs import StructureGraph, MoleculeGraph
from pymatgen.analysis.local_env import MinimumDistanceNN, CrystalNN
from pymatgen.core.periodic_table import Element

from emmet.core.symmetry import SymmetryData
from emmet.stubs import Composition, Structure

import numpy as np
from pymatgen.io.ase import AseAtomsAdaptor
from dscribe.descriptors import SOAP as SOAP_describe

DUMMY_SPECIES = "Si"
NDIM = 360  # the standard soap vector size for Si

def get_molecule(
        structure_graph: Union[StructureGraph, MoleculeGraph], n: int
) -> Molecule:
    """
    Extract all of the sites bounded to site # n of a structure graph
    Shift the molecule so the center atom is at the origin, then add
    the center atom with 0 charge so the Molecule object can be reconstructed
    Args:
        structure_graph: The Structure graph with all of the connections already drawn
        n: The specific site index to extract
    Returns:
        A Molecule object that represents the local environment of the site
    """
    nn_sites = [site_.site for site_ in structure_graph.get_connected_sites(n)]
    for site_ in nn_sites:
        site_.properties["charge"] = (0,)
        site_.properties["magmom"] = 0.0
    mol = Molecule.from_sites(nn_sites)
    mol.translate_sites(None, -structure_graph.structure[n].coords)

    mol.insert(
        i=0,
        species=structure_graph.structure[n].species_string,
        coords=[0, 0, 0],
        properties={"magmom": -0.0, "charge": (0,)},
    )
    return mol

class Dscriber(MSONable):
    def __init__(
            self,
            rcut: float = 7,
            nmax: int = 8,
            lmax: int = 9,
            nn_strat: str = "crystalnn",
            soap_scale: float = None,
    ):
        self.nn_strat = nn_strat

        if nn_strat == "cutoff":
            self.strategy = MinimumDistanceNN(tol=0, cutoff=rcut, get_all_sites=True)
        else:
            self.strategy = CrystalNN(
                distance_cutoffs=None, x_diff_weight=0.0, porous_adjustment=False
            )
        self.rcut = rcut
        self.lmax = lmax
        self.nmax = nmax
        self.adaptor = AseAtomsAdaptor()
        self.soap = SOAP_describe(
            species=[DUMMY_SPECIES],
            rcut=rcut,
            nmax=nmax,
            lmax=lmax,
            periodic=False,
            sparse=False,
        )
        self.soap_scale = soap_scale

    def get_soap(self, molecule):
        """
        Obtain the soap parameter for the molecule that represents the site
        Args:
            molecule: pymatgen molecule object that represents the data extract at a local environment
        Returns:
            The soap vector representation
        """
        tmp_mol_ = molecule.copy()
        for el in tmp_mol_.composition.elements:
            tmp_mol_.replace_species({str(el): DUMMY_SPECIES})
        if np.linalg.norm(tmp_mol_[0].coords) != 0:
            raise ValueError("The first atom must be at the origin")
        if len(molecule) <= 1:
            return [0] * self.soap.get_number_of_features()
        if self.soap_scale is not None:
            avg_dist = np.sum(
                [np.linalg.norm(isite.coords) for isite in tmp_mol_.sites]
            ) / (len(tmp_mol_) - 1)
            for i_site in tmp_mol_[1:]:
                i_site.coords *= self.soap_scale / avg_dist

        ase_struct = self.adaptor.get_atoms(tmp_mol_)
        soap_res = self.soap.create(ase_struct)
        return soap_res[0]

    def soap_vec_from_structure(self, structure):
        """

        Args:
            structure: pymatgen structure object
        Returns:
            The site specific soap descriptors
            The average soap vector representation
        """
        s_graph = StructureGraph.with_local_env_strategy(structure, self.strategy)
        site_res = []
        for j in range(len(structure)):
            molecule = get_molecule(s_graph, j)
            site_res.append(
                {
                    "local_graph": molecule.as_dict(),
                    "soap_vec": self.get_soap(molecule),
                    "s_graph": s_graph,
                }
            )
        vecs = np.array([loc_env["soap_vec"] for loc_env in site_res["site_data"]])
        return site_res, np.average(vecs, axis=0)

