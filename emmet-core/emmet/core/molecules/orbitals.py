import warnings
from itertools import groupby
from typing import List, Union
from datetime import datetime

import numpy as np
from pydantic import Field

from monty.json import MSONable

from pymatgen.core.structure import Molecule

from emmet.core.mpid import MPID
from emmet.core.structure import MoleculeMetadata
from emmet.core.material import PropertyOrigin
from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


class NaturalPopulation(MSONable):
    def __init__(self,
                 atom_index: int,
                 core_electrons: float,
                 valence_electrons: float,
                 rydberg_electrons: float,
                 total_electrons: float
                 ):

        """
        Basic description of an atomic electron population.

        :param atom_index (int):
        :param core_electrons (float): Number of core electrons on this atom
        :param valence_electrons (float): Number of valence electrons on this atom
        :param rydberg_electrons (float): Number of Rydberg electrons on this atom
        :param total_electrons (float): Total number of electrons on this atom
        """

        self.atom_index = atom_index
        self.core_electrons = core_electrons
        self.valence_electrons = valence_electrons
        self.rydberg_electrons = rydberg_electrons
        self.total_electrons = total_electrons


class LonePair(MSONable):
    def __init__(self,
                 index: int,
                 atom_index: int,
                 s_character: float,
                 p_character: float,
                 d_character: float,
                 f_character: float,
                 occupancy: float,
                 lp_type: str
                 ):
        """
        Basic description of a lone pair (LP) natural bonding orbital.

        :param index (int): Lone pair index from NBO
        :param atom_index (int):
        :param s_character (float): What fraction of this orbital is s-like in nature.
        :param p_character (float): What fraction of this orbital is p-like in nature.
        :param d_character (float): What fraction of this orbital is d-like in nature.
        :param f_character (float): What fraction of this orbital is f-like in nature.
        :param occupancy (float): Total electron occupancy of this lone pair
        :param lp_type (str): Description of this lone pair (ex: "LV" for "lone valence")
        """

        self.index = index
        self.atom_index = atom_index
        self.s_character = s_character
        self.p_character = p_character
        self.d_character = d_character
        self.f_character = f_character
        self.occupancy = occupancy
        self.type = lp_type


class Bond(MSONable):
    def __init__(self,
                 index: int,
                 atom1_index: int,
                 atom2_index: int,
                 atom1_s_character: float,
                 atom2_s_character: float,
                 atom1_p_character: float,
                 atom2_p_character: float,
                 atom1_d_character: float,
                 atom2_d_character: float,
                 atom1_f_character: float,
                 atom2_f_character: float,
                 atom1_polarization: float,
                 atom2_polarization: float,
                 atom1_polarization_coeff: float,
                 atom2_polarization_coeff: float,
                 occupancy: float,
                 bond_type: str
                 ):
        """
        Basic description of a bond (BD) natural bonding orbital.

        :param index: Bond orbital index from NBO
        :param atom1_index: Index of first atom involved in this orbital
        :param atom2_index: Index of second atom involved in this orbital
        :param atom1_s_character: What fraction of this orbital comes from atom 1 s electrons
        :param atom2_s_character: What fraction of this orbital comes from atom 2 s electrons
        :param atom1_p_character: What fraction of this orbital comes from atom 1 p electrons
        :param atom2_p_character: What fraction of this orbital comes from atom 2 p electrons
        :param atom1_d_character: What fraction of this orbital comes from atom 1 d electrons
        :param atom2_d_character: What fraction of this orbital comes from atom 2 d electrons
        :param atom1_f_character: What fraction of this orbital comes from atom 1 f electrons
        :param atom2_f_character: What fraction of this orbital comes from atom 2 f electrons
        :param atom1_polarization: Percentage of polarization from atom 1
        :param atom2_polarization: Percentage of polarization from atom 2
        :param atom1_polarization_coeff: Polarization coefficient of atom 1
        :param atom2_polarization_coeff: Polarization coefficient of atom 2
        :param occupancy: Total electron occupancy of this orbital
        :param bond_type: Description of this bonding orbital (ex: BD for bonding,
            BD* for anti-bonding)
        """

        self.index = index
        self.atom1_index = atom1_index
        self.atom2_index = atom2_index
        self.atom1_s_character = atom1_s_character
        self.atom2_s_character = atom2_s_character
        self.atom1_p_character = atom1_p_character
        self.atom2_p_character = atom2_p_character
        self.atom1_d_character = atom1_d_character
        self.atom2_d_character = atom2_d_character
        self.atom1_f_character = atom1_f_character
        self.atom2_f_character = atom2_f_character
        self.atom1_polarization = atom1_polarization
        self.atom2_polarization = atom2_polarization
        self.atom1_polarization_coeff = atom1_polarization_coeff
        self.atom2_polarization_coeff = atom2_polarization_coeff
        self.occupancy = occupancy
        self.type = bond_type


class Interaction(MSONable):
    def __init__(self,
                 donor: Union[LonePair, Bond],
                 acceptor: Union[LonePair, Bond],
                 perturbation_energy: float,
                 energy_difference: float,
                 fock_element: float
                 ):

        self.donor_index = donor.index
        self.acceptor_index = acceptor.index

        self.donor_type = donor.type
        self.acceptor_type = acceptor.type

        if isinstance(donor, LonePair):
            self.donor_atom_indices = (donor.atom_index, None)
        else:
            self.donor_atom_indices = (donor.atom1_index, donor.atom2_index)

        if isinstance(acceptor, LonePair):
            self.acceptor_atom_indices = (acceptor.atom_index, None)
        else:
            self.acceptor_atom_indices = (acceptor.atom1_index, acceptor.atom2_index)

        self.perturbation_energy = perturbation_energy
        self.energy_difference = energy_difference
        self.fock_element = fock_element


class OrbitalDoc(PropertyDoc):

    property_name = "natural bonding orbitals"

    open_shell: bool = Field(
        description="Is this molecule open-shell (spin multiplicity != 1)?"
    )

    population: List[NaturalPopulation] = Field(
        description="Natural electron populations of the molecule"
    )

    alpha_population: List[NaturalPopulation] = Field(
        None,
        description="Natural electron populations of the alpha electrons of the molecule"
    )

    beta_population: List[NaturalPopulation] = Field(
        None,
        description="Natural electron populations of the beta electrons of the molecule"
    )

    