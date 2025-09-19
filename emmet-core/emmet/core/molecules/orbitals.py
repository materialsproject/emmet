from __future__ import annotations

import re
from hashlib import blake2b
from typing import TYPE_CHECKING

from monty.json import MSONable
from pydantic import Field

from emmet.core.molecules import MolPropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPculeID
from emmet.core.qchem.task import TaskDocument
from emmet.core.utils import set_msonable_type_adapter

if TYPE_CHECKING:
    from typing import Any

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@set_msonable_type_adapter
class NaturalPopulation(MSONable):
    def __init__(
        self,
        atom_index: int,
        core_electrons: float,
        valence_electrons: float,
        rydberg_electrons: float,
        total_electrons: float,
    ):
        """
        Basic description of an atomic electron population.

        :param atom_index (int):
        :param core_electrons (float): Number of core electrons on this atom
        :param valence_electrons (float): Number of valence electrons on this atom
        :param rydberg_electrons (float): Number of Rydberg electrons on this atom
        :param total_electrons (float): Total number of electrons on this atom
        """

        self.atom_index = int(atom_index)
        self.core_electrons = float(core_electrons)
        self.valence_electrons = float(valence_electrons)
        self.rydberg_electrons = float(rydberg_electrons)
        self.total_electrons = float(total_electrons)


@set_msonable_type_adapter
class LonePair(MSONable):
    def __init__(
        self,
        index: int,
        number: int,
        atom_index: int,
        s_character: float,
        p_character: float,
        d_character: float,
        f_character: float,
        occupancy: float,
        type_code: str,
    ):
        """
        Basic description of a lone pair (LP) natural bonding orbital.

        :param index (int): Lone pair index from NBO. 1-indexed
        :param number (int): Another index, for cases where there are multiple lone
            pairs on an atom. 1-indexed
        :param atom_index (int): 0-indexed
        :param s_character (float): What fraction of this orbital is s-like in nature.
        :param p_character (float): What fraction of this orbital is p-like in nature.
        :param d_character (float): What fraction of this orbital is d-like in nature.
        :param f_character (float): What fraction of this orbital is f-like in nature.
        :param occupancy (float): Total electron occupancy of this lone pair
        :param type_code (str): Description of this lone pair (ex: "LV" for "lone valence")
        """

        self.index = int(index)
        self.number = int(number)
        self.atom_index = int(atom_index)
        self.s_character = float(s_character)
        self.p_character = float(p_character)
        self.d_character = float(d_character)
        self.f_character = float(f_character)
        self.occupancy = float(occupancy)
        self.type_code = type_code


@set_msonable_type_adapter
class Bond(MSONable):
    def __init__(
        self,
        index: int,
        number: int,
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
        type_code: str,
    ):
        """
        Basic description of a bond (BD) natural bonding orbital.

        :param index: Bond orbital index from NBO. 1-indexed.
        :param number: Another index, for cases where there are multiple bonds
            between two atoms. 1-indexed
        :param atom1_index: Index of first atom involved in this orbital. 0-indexed
        :param atom2_index: Index of second atom involved in this orbital. 0-indexed
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
        :param type_code: Description of this bonding orbital (ex: BD for bonding,
            BD* for anti-bonding)
        """

        self.index = int(index)
        self.number = int(number)
        self.atom1_index = int(atom1_index)
        self.atom2_index = int(atom2_index)
        self.atom1_s_character = float(atom1_s_character)
        self.atom2_s_character = float(atom2_s_character)
        self.atom1_p_character = float(atom1_p_character)
        self.atom2_p_character = float(atom2_p_character)
        self.atom1_d_character = float(atom1_d_character)
        self.atom2_d_character = float(atom2_d_character)
        self.atom1_f_character = float(atom1_f_character)
        self.atom2_f_character = float(atom2_f_character)
        self.atom1_polarization = float(atom1_polarization)
        self.atom2_polarization = float(atom2_polarization)
        self.atom1_polarization_coeff = float(atom1_polarization_coeff)
        self.atom2_polarization_coeff = float(atom2_polarization_coeff)
        self.occupancy = float(occupancy)
        self.type_code = type_code


@set_msonable_type_adapter
class ThreeCenterBond(MSONable):
    def __init__(
        self,
        index: int,
        number: int,
        atom1_index: int,
        atom2_index: int,
        atom3_index: int,
        atom1_s_character: float,
        atom2_s_character: float,
        atom3_s_character: float,
        atom1_p_character: float,
        atom2_p_character: float,
        atom3_p_character: float,
        atom1_d_character: float,
        atom2_d_character: float,
        atom3_d_character: float,
        atom1_f_character: float,
        atom2_f_character: float,
        atom3_f_character: float,
        atom1_polarization: float,
        atom2_polarization: float,
        atom3_polarization: float,
        atom1_polarization_coeff: float,
        atom2_polarization_coeff: float,
        atom3_polarization_coeff: float,
        occupancy: float,
        type_code: str,
    ):
        """
        Basic description of a three-center bond (3C) natural bonding orbital.

        :param index: Bond orbital index from NBO. 1-indexed.
        :param number: Another index, for cases where there are multiple bonds
            between two atoms. 1-indexed
        :param atom1_index: Index of first atom involved in this orbital. 0-indexed
        :param atom2_index: Index of second atom involved in this orbital. 0-indexed
        :param atom3_index: Index of third atom involved in this orbital. 0-indexed
        :param atom1_s_character: What fraction of this orbital comes from atom 1 s electrons
        :param atom2_s_character: What fraction of this orbital comes from atom 2 s electrons
        :param atom3_s_character: What fraction of this orbital comes from atom 3 s electrons
        :param atom1_p_character: What fraction of this orbital comes from atom 1 p electrons
        :param atom2_p_character: What fraction of this orbital comes from atom 2 p electrons
        :param atom3_p_character: What fraction of this orbital comes from atom 3 p electrons
        :param atom1_d_character: What fraction of this orbital comes from atom 1 d electrons
        :param atom2_d_character: What fraction of this orbital comes from atom 2 d electrons
        :param atom3_d_character: What fraction of this orbital comes from atom 3 d electrons
        :param atom1_f_character: What fraction of this orbital comes from atom 1 f electrons
        :param atom2_f_character: What fraction of this orbital comes from atom 2 f electrons
        :param atom3_f_character: What fraction of this orbital comes from atom 3 f electrons
        :param atom1_polarization: Percentage of polarization from atom 1
        :param atom2_polarization: Percentage of polarization from atom 2
        :param atom3_polarization: Percentage of polarization from atom 3
        :param atom1_polarization_coeff: Polarization coefficient of atom 1
        :param atom2_polarization_coeff: Polarization coefficient of atom 2
        :param atom3_polarization_coeff: Polarization coefficient of atom 3
        :param occupancy: Total electron occupancy of this orbital
        :param type_code: Description of this bonding orbital (ex: 3C for three-center bond,
            3C* for three-center anti-bond)
        """

        self.index = int(index)
        self.number = int(number)
        self.atom1_index = int(atom1_index)
        self.atom2_index = int(atom2_index)
        self.atom3_index = int(atom3_index)
        self.atom1_s_character = float(atom1_s_character)
        self.atom2_s_character = float(atom2_s_character)
        self.atom3_s_character = float(atom3_s_character)
        self.atom1_p_character = float(atom1_p_character)
        self.atom2_p_character = float(atom2_p_character)
        self.atom3_p_character = float(atom3_p_character)
        self.atom1_d_character = float(atom1_d_character)
        self.atom2_d_character = float(atom2_d_character)
        self.atom3_d_character = float(atom3_d_character)
        self.atom1_f_character = float(atom1_f_character)
        self.atom2_f_character = float(atom2_f_character)
        self.atom3_f_character = float(atom3_f_character)
        self.atom1_polarization = float(atom1_polarization)
        self.atom2_polarization = float(atom2_polarization)
        self.atom3_polarization = float(atom3_polarization)
        self.atom1_polarization_coeff = float(atom1_polarization_coeff)
        self.atom2_polarization_coeff = float(atom2_polarization_coeff)
        self.atom3_polarization_coeff = float(atom3_polarization_coeff)
        self.occupancy = float(occupancy)
        self.type_code = type_code


@set_msonable_type_adapter
class Hyperbond(MSONable):
    def __init__(
        self,
        index: int,
        atom1_index: int,
        atom2_index: int,
        atom3_index: int,
        fraction_12: float,
        fraction_23: float,
        occupancy: float,
        bond_index_12: int,
        lp_index_3: int,
        hybrid_index_1: int,
        hybrid_index_2: int,
        hybrid_index_3: int,
    ):
        """
        Basic description of a three-center, four-electron hyperbond (3CHB).

        :param index: Bond orbital index from NBO. 1-indexed.
        :param atom1_index: Index of first atom involved in this orbital. 0-indexed
        :param atom2_index: Index of second atom involved in this orbital. 0-indexed
        :param atom3_index: Index of third atom involved in this orbital. 0-indexed
        :param fraction_12: What fraction of this hyperbond comes from the bond between atoms 1 and 2
        :param fraction_23: What fraction of this hyperbond comes from the bond between atoms 2 and 3
        :param occupancy: Total electron occupancy of this orbital
        :param bond_index_12: Index of the bond orbital between atoms used 1 and 2 used to make this hyperbond
        :param lp_index_3: Index of the LP on atom 3 used to make this hyperbond
        :hybrid_index_1: Index of the natural hybrid orbital (NHO) on atom 1 used to make this hyperbond
        :hybrid_index_2: Index of the natural hybrid orbital (NHO) on atom 2 used to make this hyperbond
        :hybrid_index_3: Index of the natural hybrid orbital (NHO) on atom 3 used to make this hyperbond
        """

        self.index = int(index)
        self.atom1_index = int(atom1_index)
        self.atom2_index = int(atom2_index)
        self.atom3_index = int(atom3_index)
        self.fraction_12 = float(fraction_12)
        self.fraction_23 = float(fraction_23)
        self.occupancy = float(occupancy)
        self.bond_index_12 = int(bond_index_12)
        self.lp_index_3 = int(lp_index_3)
        self.hybrid_index_1 = int(hybrid_index_1)
        self.hybrid_index_2 = int(hybrid_index_2)
        self.hybrid_index_3 = int(hybrid_index_3)


@set_msonable_type_adapter
class Interaction(MSONable):
    def __init__(
        self,
        perturbation_energy: float,
        energy_difference: float,
        fock_element: float,
        donor_index: int,
        acceptor_index: int,
        donor_type: str,
        acceptor_type: str,
        donor_atom1_index: int,
        acceptor_atom1_index: int,
        donor_atom2_index: int | None = None,
        acceptor_atom2_index: int | None = None,
        donor_atom3_index: int | None = None,
        acceptor_atom3_index: int | None = None,
    ):
        """
        Description of an interaction between two orbitals

        :param perturbation_energy: second-order perturbation energy, in kcal/mol
        :param energy_difference: difference in energy between the interacting orbitals, in Ha
        :param fock_element: Fock matrix element corresponding to this interaction, in a.u.
        :donor_index: Index of the donating orbital
        :acceptor_index: Index of the accepting orbital
        :donor_type: Type code for the donating orbital
        :acceptor_type: Type code for the accepting orbital
        :donor_atom1_index: Index of the first atom involved in the donor orbital
        :acceptor_atom1_index: Index of the first atom involved in the acceptor orbital
        :donor_atom2_index: Index of the second atom involved in the donor orbital
        :acceptor_atom2_index: Index of the second atom involved in the acceptor orbital
        :donor_atom3_index: Index of the third atom involved in the donor orbital
        :acceptor_atom3_index: Index of the third atom involved in the acceptor orbital
        """

        self.donor_index = int(donor_index)
        self.acceptor_index = int(acceptor_index)

        self.donor_type = donor_type
        self.acceptor_type = acceptor_type

        if isinstance(donor_atom2_index, int):
            if donor_atom2_index < 0:
                donor2 = None
            else:
                donor2 = int(donor_atom2_index)
        else:
            donor2 = None

        if isinstance(acceptor_atom2_index, int):
            if acceptor_atom2_index < 0:
                acceptor2 = None
            else:
                acceptor2 = int(acceptor_atom2_index)
        else:
            acceptor2 = None

        if isinstance(donor_atom3_index, int):
            # Not sure if this is actual possible
            if donor_atom3_index < 0:
                donor3 = None
            else:
                donor3 = int(donor_atom3_index)
        else:
            donor3 = None

        if isinstance(acceptor_atom3_index, int):
            # Similarly, not sure if this is important
            if acceptor_atom3_index < 0:
                acceptor3 = None
            else:
                acceptor3 = int(acceptor_atom3_index)
        else:
            acceptor3 = None

        self.donor_atom_indices = [
            index
            for index in [int(donor_atom1_index), donor2, donor3]
            if index is not None
        ]
        self.acceptor_atom_indices = [
            index
            for index in [int(acceptor_atom1_index), acceptor2, acceptor3]
            if index is not None
        ]

        self.perturbation_energy = float(perturbation_energy)
        self.energy_difference = float(energy_difference)
        self.fock_element = float(fock_element)

    def as_dict(self):
        return {
            "@module": self.__class__.__module__,
            "@class": self.__class__.__name__,
            "donor_index": self.donor_index,
            "acceptor_index": self.acceptor_index,
            "donor_type": self.donor_type,
            "acceptor_type": self.acceptor_type,
            "donor_atom_indices": self.donor_atom_indices,
            "acceptor_atom_indices": self.acceptor_atom_indices,
            "perturbation_energy": self.perturbation_energy,
            "energy_difference": self.energy_difference,
            "fock_element": self.fock_element,
        }

    @classmethod
    def from_dict(cls, d):
        donor_inds = d["donor_atom_indices"]
        acceptor_inds = d["acceptor_atom_indices"]

        if len(donor_inds) < 2:
            donor_inds += [None, None]
        elif len(donor_inds) < 3:
            donor_inds += [None]

        if len(acceptor_inds) < 2:
            acceptor_inds += [None, None]
        elif len(acceptor_inds) < 3:
            acceptor_inds += [None]

        return cls(
            d["perturbation_energy"],
            d["energy_difference"],
            d["fock_element"],
            d["donor_index"],
            d["acceptor_index"],
            d["donor_type"],
            d["acceptor_type"],
            donor_inds[0],
            acceptor_inds[0],
            donor_inds[1],
            acceptor_inds[1],
            donor_inds[2],
            acceptor_inds[2],
        )


class OrbitalDoc(PropertyDoc):
    property_name: str = "natural bonding orbitals"

    # Always populated - closed-shell and open-shell
    open_shell: bool = Field(
        ..., description="Is this molecule open-shell (spin multiplicity != 1)?"
    )

    nbo_population: list[NaturalPopulation] = Field(
        ..., description="Natural electron populations of the molecule"
    )

    # Populated for closed-shell molecules
    nbo_lone_pairs: list[LonePair] | None = Field(
        None, description="Lone pair orbitals of a closed-shell molecule"
    )

    nbo_bonds: list[Bond] | None = Field(
        None, description="Bond-like orbitals of a closed-shell molecule"
    )

    nbo_three_center_bonds: list[ThreeCenterBond] | None = Field(
        None, description="Three-center bond-like orbitals of a closed-shell molecule"
    )

    nbo_hyperbonds: list[Hyperbond] | None = Field(
        None, description="3-center hyperbond-like orbitals of a closed-shell molecule"
    )

    nbo_interactions: list[Interaction] | None = Field(
        None, description="Orbital-orbital interactions of a closed-shell molecule"
    )

    # Populated for open-shell molecules
    alpha_population: list[NaturalPopulation] | None = Field(
        None,
        description="Natural electron populations of the alpha electrons of an "
        "open-shell molecule",
    )
    beta_population: list[NaturalPopulation] | None = Field(
        None,
        description="Natural electron populations of the beta electrons of an "
        "open-shell molecule",
    )

    alpha_lone_pairs: list[LonePair] | None = Field(
        None, description="Alpha electron lone pair orbitals of an open-shell molecule"
    )
    beta_lone_pairs: list[LonePair] | None = Field(
        None, description="Beta electron lone pair orbitals of an open-shell molecule"
    )

    alpha_bonds: list[Bond] | None = Field(
        None, description="Alpha electron bond-like orbitals of an open-shell molecule"
    )
    beta_bonds: list[Bond] | None = Field(
        None, description="Beta electron bond-like orbitals of an open-shell molecule"
    )

    alpha_three_center_bonds: list[ThreeCenterBond] | None = Field(
        None,
        description="Alpha electron three-center bond-like orbitals of an open-shell molecule",
    )
    beta_three_center_bonds: list[ThreeCenterBond] | None = Field(
        None,
        description="Beta electron three-center bond-like orbitals of an open-shell molecule",
    )

    alpha_hyperbonds: list[Hyperbond] | None = Field(
        None,
        description="Alpha electron hyperbond-like orbitals of an open-shell molecule",
    )
    beta_hyperbonds: list[Hyperbond] | None = Field(
        None,
        description="Beta electron hyperbond-like orbitals of an open-shell molecule",
    )

    alpha_interactions: list[Interaction] | None = Field(
        None,
        description="Alpha electron orbital-orbital interactions of an open-shell molecule",
    )
    beta_interactions: list[Interaction] | None = Field(
        None,
        description="Beta electron orbital-orbital interactions of an open-shell molecule",
    )

    @staticmethod
    def get_populations(nbo: dict[str, Any], indices: list[int]):
        """
        Helper function to extract natural population information
        from NBO output

        :param nbo: Dictionary of NBO output data
        :param indices: Data subsets from which to extract natural populations
        :return: population_sets (list of lists of NaturalPopulation)
        """

        population_sets = list()

        for pop_ind in indices:
            pops = nbo["natural_populations"][pop_ind]
            population = list()
            for ind, atom_num in pops["No"].items():
                population.append(
                    NaturalPopulation(
                        atom_num - 1,
                        pops["Core"][ind],
                        pops["Valence"][ind],
                        pops["Rydberg"][ind],
                        pops["Total"][ind],
                    )
                )
            population_sets.append(population)

        return population_sets

    @staticmethod
    def get_lone_pairs(nbo: dict[str, Any], indices: list[int]):
        """
        Helper function to extract lone pair information from NBO output

        :param nbo: Dictionary of NBO output data
        :param indices: Data subsets from which to extract lone pair information
        :return: lone_pairs (list of LonePairs)
        """

        lone_pair_sets = list()

        for lp_ind in indices:
            lps = nbo["hybridization_character"][lp_ind]
            lone_pairs = list()
            for ind, orb_ind in lps.get("bond index", dict()).items():
                this_lp = LonePair(
                    orb_ind,
                    lps["orbital index"][ind],
                    int(lps["atom number"][ind]) - 1,
                    lps["s"][ind],
                    lps["p"][ind],
                    lps["d"][ind],
                    lps["f"][ind],
                    lps["occupancy"][ind],
                    lps["type"][ind],
                )
                lone_pairs.append(this_lp)
            lone_pair_sets.append(lone_pairs)

        return lone_pair_sets

    @staticmethod
    def get_bonds(nbo: dict[str, Any], indices: list[int]):
        """
        Helper function to extract bonding information from NBO output

        :param nbo: Dictionary of NBO output data
        :param indices: Data subsets from which to extract bonds
        :return: bonds (list of Bonds)
        """

        bond_sets = list()

        for bd_ind in indices:
            bds = nbo["hybridization_character"][bd_ind]
            bonds = list()
            for ind, orb_ind in bds.get("bond index", dict()).items():
                this_bond = Bond(
                    orb_ind,
                    bds["orbital index"][ind],
                    int(bds["atom 1 number"][ind]) - 1,
                    int(bds["atom 2 number"][ind]) - 1,
                    bds["atom 1 s"][ind],
                    bds["atom 2 s"][ind],
                    bds["atom 1 p"][ind],
                    bds["atom 2 p"][ind],
                    bds["atom 1 d"][ind],
                    bds["atom 2 d"][ind],
                    bds["atom 1 f"][ind],
                    bds["atom 2 f"][ind],
                    bds["atom 1 polarization"][ind],
                    bds["atom 2 polarization"][ind],
                    bds["atom 1 pol coeff"][ind],
                    bds["atom 2 pol coeff"][ind],
                    bds["occupancy"][ind],
                    bds["type"][ind],
                )
                bonds.append(this_bond)
            bond_sets.append(bonds)

        return bond_sets

    @staticmethod
    def get_three_center_bonds(nbo: dict[str, Any], indices: list[int]):
        """
        Helper function to extract bonding information from NBO output

        :param nbo: Dictionary of NBO output data
        :param indices: Data subsets from which to extract bonds
        :return: threec_bonds (list of ThreeCenterBonds)
        """

        if len(indices) == 0:
            return None

        threec_sets = list()

        for tc_ind in indices:
            tcs = nbo["hybridization_character"][tc_ind]
            threecs = list()
            for ind, orb_ind in tcs.get("bond index", dict()).items():
                this_threec = ThreeCenterBond(
                    orb_ind,
                    tcs["orbital index"][ind],
                    int(tcs["atom 1 number"][ind]) - 1,
                    int(tcs["atom 2 number"][ind]) - 1,
                    int(tcs["atom 3 number"][ind]) - 1,
                    tcs["atom 1 s"][ind],
                    tcs["atom 2 s"][ind],
                    tcs["atom 3 s"][ind],
                    tcs["atom 1 p"][ind],
                    tcs["atom 2 p"][ind],
                    tcs["atom 3 p"][ind],
                    tcs["atom 1 d"][ind],
                    tcs["atom 2 d"][ind],
                    tcs["atom 3 d"][ind],
                    tcs["atom 1 f"][ind],
                    tcs["atom 2 f"][ind],
                    tcs["atom 3 f"][ind],
                    tcs["atom 1 polarization"][ind],
                    tcs["atom 2 polarization"][ind],
                    tcs["atom 3 polarization"][ind],
                    tcs["atom 1 pol coeff"][ind],
                    tcs["atom 2 pol coeff"][ind],
                    tcs["atom 3 pol coeff"][ind],
                    tcs["occupancy"][ind],
                    tcs["type"][ind],
                )
                threecs.append(this_threec)
            threec_sets.append(threecs)

        return threec_sets

    @staticmethod
    def get_hyperbonds(nbo: dict[str, Any], indices: list[int]):
        """
        Helper function to extract hyperbond information form NBO output

        :param nbo: Dictionary of NBO output data
        :param indices: Data subsets from which to extract interactions
        :return: interactions (list of Hyperbonds)
        """

        hyperbond_sets = list()

        # No hyperbonds present
        if "hyperbonds" not in nbo or len(indices) == 0 or len(nbo["hyperbonds"]) == 0:
            return None

        for hb_ind in indices:
            # For other types of bonds, all indices must be present
            # That is, we always expect one set of orbitals for closed-shell molecules,
            # And we always expect two sets (alpha and beta) for open-shell molecules
            # Hyperbonds are different.
            # Since these are (up to) 4-electron configurations, you could have a partially occupied
            # hyperbond with only two electrons
            # And in this case, for an open-shell molecule, you may only have one set of hyperbonds
            hyperbonds = list()
            try:
                hbds = nbo["hyperbonds"][hb_ind]
            except IndexError:
                hbds = dict()
            for ind, orb_ind in hbds.get("hyperbond index", dict()).items():
                this_hyperbond = Hyperbond(
                    orb_ind,
                    int(hbds["bond atom 1 index"][ind]) - 1,
                    int(hbds["bond atom 2 index"][ind]) - 1,
                    int(hbds["bond atom 3 index"][ind]) - 1,
                    hbds["pctA-B"][ind],
                    hbds["pctB-C"][ind],
                    hbds["occ"][ind],
                    hbds["BD(A-B)"][ind],
                    hbds["LP(C)"][ind],
                    hbds["h(A)"][ind],
                    hbds["h(B)"][ind],
                    hbds["h(C)"][ind],
                )
                hyperbonds.append(this_hyperbond)
            hyperbond_sets.append(hyperbonds)

        return hyperbond_sets

    @staticmethod
    def get_interactions(nbo: dict[str, Any], indices: list[int]):
        """
        Helper function to extract orbital interaction information
        from NBO output

        :param nbo: Dictionary of NBO output data
        :param indices: Data subsets from which to extract interactions
        :return: interactions (list of Interactions)
        """

        interaction_sets = list()

        for pert_ind in indices:
            perts = nbo["perturbation_energy"][pert_ind]
            interactions = list()
            for ind in perts.get("donor bond index", list()):
                donor_atom2 = perts["donor atom 2 number"].get(ind)
                if donor_atom2 == "info_is_from_3C":
                    # There's a pretty horrible hack in the current pymatgen NBO parsers
                    # To prevent a dramatic increase in storage space, atom indices and element symbols for 3C bonds
                    # are stored using the same keys as those used for lone pairs and conventional two-center bonds
                    donor_atom1_index = (
                        int(re.sub(r"\D", "", perts["donor atom 1 symbol"][ind])) - 1
                    )
                    donor_atom2_index = (
                        int(re.sub(r"\D", "", perts["donor atom 1 number"][ind])) - 1
                    )
                    donor_atom3_index = (
                        int(re.sub(r"\D", "", perts["donor atom 2 symbol"][ind])) - 1
                    )
                else:
                    donor_atom1_index = int(perts["donor atom 1 number"][ind]) - 1
                    donor_atom3_index = None
                    if donor_atom2 is None:
                        donor_atom2_index = None
                    else:
                        donor_atom2_index = int(donor_atom2) - 1

                acceptor_atom2 = perts["acceptor atom 2 number"].get(ind)
                if acceptor_atom2 == "info_is_from_3C":
                    acceptor_atom1_index = (
                        int(re.sub(r"\D", "", perts["acceptor atom 1 symbol"][ind])) - 1
                    )
                    acceptor_atom2_index = (
                        int(re.sub(r"\D", "", perts["acceptor atom 1 number"][ind])) - 1
                    )
                    acceptor_atom3_index = (
                        int(re.sub(r"\D", "", perts["acceptor atom 2 symbol"][ind])) - 1
                    )
                else:
                    acceptor_atom1_index = int(perts["acceptor atom 1 number"][ind]) - 1
                    acceptor_atom3_index = None
                    if acceptor_atom2 is None:
                        acceptor_atom2_index = None
                    else:
                        acceptor_atom2_index = int(acceptor_atom2) - 1

                this_inter = Interaction(
                    perts["perturbation energy"][ind],
                    perts["energy difference"][ind],
                    perts["fock matrix element"][ind],
                    int(perts["donor bond index"][ind]),
                    int(perts["acceptor bond index"][ind]),
                    perts["donor type"][ind],
                    perts["acceptor type"][ind],
                    donor_atom1_index,
                    acceptor_atom1_index,
                    donor_atom2_index,
                    acceptor_atom2_index,
                    donor_atom3_index,
                    acceptor_atom3_index,
                )

                interactions.append(this_inter)
            interaction_sets.append(interactions)

        return interaction_sets

    @classmethod
    def from_task(
        cls,
        task: TaskDocument,
        molecule_id: MPculeID,
        deprecated: bool = False,
        **kwargs,
    ):  # type: ignore[override]
        """
        Construct an orbital document from a task

        :param task: document from which vibrational properties can be extracted
        :param molecule_id: MPculeID
        :param deprecated: bool. Is this document deprecated?
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        if task.output.nbo is None:
            raise ValueError("No NBO output in task {}!".format(task.task_id))
        elif not (
            task.orig["rem"].get("run_nbo6", False)
            or task.orig["rem"].get("nbo_external", False)
        ):
            raise ValueError("Only NBO7 is allowed!")

        nbo = task.output.nbo

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        spin = mol.spin_multiplicity

        # Closed-shell
        if int(spin) == 1:
            pops_inds = [0]
            lps_inds = [0]
            bds_inds = [1]
            if "hyperbonds" in nbo:
                # New parser, with three-center bonds
                tc_inds = [2]
            else:
                # Old parser - no three-center bonds
                tc_inds = list()
            hbds_inds = [0]
            perts_inds = [0]

        # Open-shell
        else:
            pops_inds = [0, 1, 2]
            if len(nbo.get("hybridization_character", [0, 0, 0, 0])) == 4:
                # Old parser - no three-center bonds
                lps_inds = [0, 2]
                bds_inds = [1, 3]
                tc_inds = list()
            else:
                # New parser - with three-center bonds
                lps_inds = [0, 3]
                bds_inds = [1, 4]
                tc_inds = [2, 5]
            hbds_inds = [0, 1]
            perts_inds = [0, 1]

        for dset, inds in [
            ("natural_populations", pops_inds),
            ("hybridization_character", lps_inds + bds_inds + tc_inds),
            ("perturbation_energy", perts_inds),
        ]:
            if len(nbo.get(dset, list())) <= inds[-1]:
                return

        population_sets = cls.get_populations(nbo, pops_inds)
        lone_pair_sets = cls.get_lone_pairs(nbo, lps_inds)
        bond_sets = cls.get_bonds(nbo, bds_inds)
        threec_sets = cls.get_three_center_bonds(nbo, tc_inds)
        hyperbond_sets = cls.get_hyperbonds(nbo, hbds_inds)
        interaction_sets = cls.get_interactions(nbo, perts_inds)

        if not (
            task.orig["rem"].get("run_nbo6")
            or task.orig["rem"].get("nbo_external", False)
        ):
            warnings = ["Using NBO5"]
        else:
            warnings = list()

        id_string = (
            f"natural_bonding_orbitals-{molecule_id}-{task.task_id}-{task.lot_solvent}"
        )
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()

        if int(spin) == 1:
            if threec_sets is None:
                threec = None
            else:
                threec = threec_sets[0]

            if hyperbond_sets is None:
                hyperbond = None
            else:
                hyperbond = hyperbond_sets[0]

            return super().from_molecule(
                meta_molecule=mol,
                property_id=property_id,
                molecule_id=molecule_id,
                level_of_theory=task.level_of_theory,
                solvent=task.solvent,
                lot_solvent=task.lot_solvent,
                open_shell=False,
                nbo_population=population_sets[0],
                nbo_lone_pairs=lone_pair_sets[0],
                nbo_bonds=bond_sets[0],
                nbo_three_center_bonds=threec,
                nbo_hyperbonds=hyperbond,
                nbo_interactions=interaction_sets[0],
                origins=[
                    MolPropertyOrigin(
                        name="natural_bonding_orbitals", task_id=task.task_id
                    )
                ],
                warnings=warnings,
                deprecated=deprecated,
                **kwargs,
            )

        else:
            if threec_sets is None:
                threec_alpha = None
                threec_beta = None
            else:
                threec_alpha = threec_sets[0]
                threec_beta = threec_sets[1]

            if hyperbond_sets is None:
                hyperbond_alpha = None
                hyperbond_beta = None
            else:
                hyperbond_alpha = hyperbond_sets[0]
                hyperbond_beta = hyperbond_sets[1]

            return super().from_molecule(
                meta_molecule=mol,
                property_id=property_id,
                molecule_id=molecule_id,
                level_of_theory=task.level_of_theory,
                solvent=task.solvent,
                lot_solvent=task.lot_solvent,
                open_shell=True,
                nbo_population=population_sets[0],
                alpha_population=population_sets[1],
                beta_population=population_sets[2],
                alpha_lone_pairs=lone_pair_sets[0],
                beta_lone_pairs=lone_pair_sets[1],
                alpha_bonds=bond_sets[0],
                beta_bonds=bond_sets[1],
                alpha_three_center_bonds=threec_alpha,
                beta_three_center_bonds=threec_beta,
                alpha_hyperbonds=hyperbond_alpha,
                beta_hyperbonds=hyperbond_beta,
                alpha_interactions=interaction_sets[0],
                beta_interactions=interaction_sets[1],
                origins=[
                    MolPropertyOrigin(
                        name="natural bonding orbitals", task_id=task.task_id
                    )
                ],
                warnings=warnings,
                deprecated=deprecated,
                **kwargs,
            )
