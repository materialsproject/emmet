from typing import List, Optional, Dict, Any

from pydantic import Field

from monty.json import MSONable

from emmet.core.mpid import MPID
from emmet.core.material import PropertyOrigin
from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


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
        donor_atom2_index: Optional[int] = None,
        acceptor_atom2_index: Optional[int] = None,
    ):

        self.donor_index = int(donor_index)
        self.acceptor_index = int(acceptor_index)

        self.donor_type = donor_type
        self.acceptor_type = acceptor_type

        if isinstance(donor_atom2_index, int):
            donor2 = int(donor_atom2_index)
        else:
            donor2 = None

        if isinstance(acceptor_atom2_index, int):
            acceptor2 = int(acceptor_atom2_index)
        else:
            acceptor2 = None

        self.donor_atom_indices = (int(donor_atom1_index), donor2)
        self.acceptor_atom_indices = (int(acceptor_atom1_index), acceptor2)

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
        return cls(
            d["perturbation_energy"],
            d["energy_difference"],
            d["fock_element"],
            d["donor_index"],
            d["acceptor_index"],
            d["donor_type"],
            d["acceptor_type"],
            d["donor_atom_indices"][0],
            d["acceptor_atom_indices"][0],
            d["donor_atom_indices"][1],
            d["acceptor_atom_indices"][1],
        )


class OrbitalDoc(PropertyDoc):

    property_name = "natural bonding orbitals"

    # Always populated - closed-shell and open-shell
    open_shell: bool = Field(
        ..., description="Is this molecule open-shell (spin multiplicity != 1)?"
    )

    nbo_population: List[NaturalPopulation] = Field(
        ..., description="Natural electron populations of the molecule"
    )

    # Populated for closed-shell molecules
    nbo_lone_pairs: List[LonePair] = Field(
        None, description="Lone pair orbitals of a closed-shell molecule"
    )

    nbo_bonds: List[Bond] = Field(
        None, description="Bond-like orbitals of a closed-shell molecule"
    )

    nbo_interactions: List[Interaction] = Field(
        None, description="Orbital-orbital interactions of a closed-shell molecule"
    )

    # Populated for open-shell molecules
    alpha_population: List[NaturalPopulation] = Field(
        None,
        description="Natural electron populations of the alpha electrons of an "
        "open-shell molecule",
    )
    beta_population: List[NaturalPopulation] = Field(
        None,
        description="Natural electron populations of the beta electrons of an "
        "open-shell molecule",
    )

    alpha_lone_pairs: List[LonePair] = Field(
        None, description="Alpha electron lone pair orbitals of an open-shell molecule"
    )
    beta_lone_pairs: List[LonePair] = Field(
        None, description="Beta electron lone pair orbitals of an open-shell molecule"
    )

    alpha_bonds: List[Bond] = Field(
        None, description="Alpha electron bond-like orbitals of an open-shell molecule"
    )
    beta_bonds: List[Bond] = Field(
        None, description="Beta electron bond-like orbitals of an open-shell molecule"
    )

    alpha_interactions: List[Interaction] = Field(
        None,
        description="Alpha electron orbital-orbital interactions of an open-shell molecule",
    )
    beta_interactions: List[Interaction] = Field(
        None,
        description="Beta electron orbital-orbital interactions of an open-shell molecule",
    )

    @staticmethod
    def get_populations(nbo: Dict[str, Any], indices: List[int]):
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
    def get_lone_pairs(nbo: Dict[str, Any], indices: List[int]):
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
    def get_bonds(nbo: Dict[str, Any], indices: List[int]):
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
    def get_interactions(nbo: Dict[str, Any], indices: List[int]):
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

                if perts["donor atom 2 number"].get(ind) is None:
                    donor_atom2_number = None
                else:
                    donor_atom2_number = int(perts["donor atom 2 number"][ind]) - 1

                if perts["acceptor atom 2 number"].get(ind) is None:
                    acceptor_atom2_number = None
                else:
                    acceptor_atom2_number = (
                        int(perts["acceptor atom 2 number"][ind]) - 1
                    )

                this_inter = Interaction(
                    perts["perturbation energy"][ind],
                    perts["energy difference"][ind],
                    perts["fock matrix element"][ind],
                    int(perts["donor bond index"][ind]),
                    int(perts["acceptor bond index"][ind]),
                    perts["donor type"][ind],
                    perts["acceptor type"][ind],
                    int(perts["donor atom 1 number"][ind]) - 1,
                    int(perts["acceptor atom 1 number"][ind]) - 1,
                    donor_atom2_number,
                    acceptor_atom2_number,
                )

                interactions.append(this_inter)
            interaction_sets.append(interactions)

        return interaction_sets

    @classmethod
    def from_task(
        cls, task: TaskDocument, molecule_id: MPID, deprecated: bool = False, **kwargs
    ):  # type: ignore[override]
        """
        Construct an orbital document from a task

        :param task: document from which vibrational properties can be extracted
        :param molecule_id: mpid
        :param deprecated: bool. Is this document deprecated?
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        if task.output.nbo is None:
            raise ValueError("No NBO output in task {}!".format(task.task_id))
        elif not task.orig["rem"].get("run_nbo6", False):
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
            perts_inds = [0]

        # Open-shell
        else:
            pops_inds = [0, 1, 2]
            lps_inds = [0, 2]
            bds_inds = [1, 3]
            perts_inds = [0, 1]

        for dset, inds in [("natural_populations", pops_inds),
                           ("hybridization_character", bds_inds),
                           ("perturbation_energy", perts_inds)]:
            if len(nbo[dset]) < inds[-1]:
                return

        population_sets = cls.get_populations(nbo, pops_inds)
        lone_pair_sets = cls.get_lone_pairs(nbo, lps_inds)
        bond_sets = cls.get_bonds(nbo, bds_inds)
        interaction_sets = cls.get_interactions(nbo, perts_inds)

        if not task.orig["rem"].get("run_nbo6"):
            warnings = ["Using NBO5"]
        else:
            warnings = list()

        if int(spin) == 1:
            return super().from_molecule(
                meta_molecule=mol,
                molecule_id=molecule_id,
                open_shell=False,
                nbo_population=population_sets[0],
                nbo_lone_pairs=lone_pair_sets[0],
                nbo_bonds=bond_sets[0],
                nbo_interactions=interaction_sets[0],
                origins=[
                    PropertyOrigin(
                        name="natural bonding orbitals", task_id=task.task_id
                    )
                ],
                deprecated=deprecated,
                warnings=warnings,
                **kwargs
            )

        else:
            return super().from_molecule(
                meta_molecule=mol,
                molecule_id=molecule_id,
                open_shell=True,
                nbo_population=population_sets[0],
                alpha_population=population_sets[1],
                beta_population=population_sets[2],
                alpha_lone_pairs=lone_pair_sets[0],
                beta_lone_pairs=lone_pair_sets[1],
                alpha_bonds=bond_sets[0],
                beta_bonds=bond_sets[1],
                alpha_interactions=interaction_sets[0],
                beta_interactions=interaction_sets[1],
                origins=[
                    PropertyOrigin(
                        name="natural bonding orbitals", task_id=task.task_id
                    )
                ],
                deprecated=deprecated,
                warnings=warnings,
                **kwargs
            )
