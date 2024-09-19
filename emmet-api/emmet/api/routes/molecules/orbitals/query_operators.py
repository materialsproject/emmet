from typing import Any, Optional, Dict
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class NBOPopulationQuery(QueryOperator):
    """
    Method to generate a query on NBO natural population data.
    """

    def query(
        self,
        electron_type_population: Optional[str] = Query(
            None,
            description="Should alpha ('alpha'), beta ('beta'), or all electrons be considered (None; default)?",
        ),
        min_core_electrons: Optional[float] = Query(
            None,
            description="Minimum number of core electrons in an atom in this molecule.",
        ),
        max_core_electrons: Optional[float] = Query(
            None,
            description="Maximum number of core electrons in an atom in this molecule.",
        ),
        min_valence_electrons: Optional[float] = Query(
            None,
            description="Minimum number of valence electrons in an atom in this molecule.",
        ),
        max_valence_electrons: Optional[float] = Query(
            None,
            description="Maximum number of valence electrons in an atom in this molecule.",
        ),
        min_rydberg_electrons: Optional[float] = Query(
            None,
            description="Minimum number of Rydberg electrons in an atom in this molecule.",
        ),
        max_rydberg_electrons: Optional[float] = Query(
            None,
            description="Maximum number of Rydberg electrons in an atom in this molecule.",
        ),
        min_total_electrons: Optional[float] = Query(
            None, description="Minimum number of electrons in an atom in this molecule."
        ),
        max_total_electrons: Optional[float] = Query(
            None, description="Maximum number of electrons in an atom in this molecule."
        ),
    ) -> STORE_PARAMS:
        crit: Dict[str, Any] = dict()  # type: ignore

        d = {
            "core_electrons": [min_core_electrons, max_core_electrons],
            "valence_electrons": [min_valence_electrons, max_valence_electrons],
            "rydberg_electrons": [min_rydberg_electrons, max_rydberg_electrons],
            "total_electrons": [min_total_electrons, max_total_electrons],
        }

        if electron_type_population is None:
            prefix = "nbo_population."
        else:
            try:
                if electron_type_population.lower() == "alpha":
                    prefix = "alpha_population."
                elif electron_type_population.lower() == "beta":
                    prefix = "beta_population."
                else:
                    raise ValueError(
                        "electron_type must be 'alpha' or 'beta' (open-shell), or None (closed-shell)!"
                    )
            except AttributeError:
                raise ValueError(
                    "electron_type must be 'alpha' or 'beta' (open-shell), or None (closed-shell)!"
                )

        for entry in d:
            key = prefix + entry
            if d[entry][0] is not None or d[entry][1] is not None:
                crit[key] = dict()

            if d[entry][0] is not None:
                crit[key]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[key]["$lte"] = d[entry][1]

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [
            ("open_shell", False),
            ("nbo_population.core_electrons", False),
            ("nbo_population.valence_electrons", False),
            ("nbo_population.rydberg_electrons", False),
            ("nbo_population.total_electrons", False),
            ("alpha_population.core_electrons", False),
            ("alpha_population.valence_electrons", False),
            ("alpha_population.rydberg_electrons", False),
            ("alpha_population.total_electrons", False),
            ("beta_population.core_electrons", False),
            ("beta_population.valence_electrons", False),
            ("beta_population.rydberg_electrons", False),
            ("beta_population.total_electrons", False),
        ]


class NBOLonePairQuery(QueryOperator):
    """
    Method to generate a query on NBO lone pair data.
    """

    def query(
        self,
        electron_type_lp: Optional[str] = Query(
            None,
            description="Should alpha ('alpha'), beta ('beta'), or all electrons be considered (None; default)?",
        ),
        lp_type: Optional[str] = Query(
            None,
            description="Type of orbital - 'LP' for 'lone pair' or 'LV' for 'lone vacant'",
        ),
        min_s_character: Optional[float] = Query(
            None,
            description="Minimum percentage of the lone pair constituted by s atomic orbitals.",
        ),
        max_s_character: Optional[float] = Query(
            None,
            description="Maximum percentage of the lone pair constituted by s atomic orbitals.",
        ),
        min_p_character: Optional[float] = Query(
            None,
            description="Minimum percentage of the lone pair constituted by p atomic orbitals.",
        ),
        max_p_character: Optional[float] = Query(
            None,
            description="Maximum percentage of the lone pair constituted by p atomic orbitals.",
        ),
        min_d_character: Optional[float] = Query(
            None,
            description="Minimum percentage of the lone pair constituted by d atomic orbitals.",
        ),
        max_d_character: Optional[float] = Query(
            None,
            description="Maximum percentage of the lone pair constituted by d atomic orbitals.",
        ),
        min_f_character: Optional[float] = Query(
            None,
            description="Minimum percentage of the lone pair constituted by f atomic orbitals.",
        ),
        max_f_character: Optional[float] = Query(
            None,
            description="Maximum percentage of the lone pair constituted by f atomic orbitals.",
        ),
        min_lp_occupancy: Optional[float] = Query(
            None, description="Minimum number of electrons in the lone pair."
        ),
        max_lp_occupancy: Optional[float] = Query(
            None, description="Maximum number of electrons in the lone pair."
        ),
    ) -> STORE_PARAMS:
        crit: Dict[str, Any] = dict()  # type: ignore

        d = {
            "s_character": [min_s_character, max_s_character],
            "p_character": [min_p_character, max_p_character],
            "d_character": [min_d_character, max_d_character],
            "f_character": [min_f_character, max_f_character],
            "occupancy": [min_lp_occupancy, max_lp_occupancy],
        }

        if electron_type_lp is None:
            prefix = "nbo_lone_pairs."
        else:
            try:
                if electron_type_lp.lower() == "alpha":
                    prefix = "alpha_lone_pairs."
                elif electron_type_lp.lower() == "beta":
                    prefix = "beta_lone_pairs."
                else:
                    raise ValueError(
                        "electron_type must be 'alpha' or 'beta' (open-shell), or None (closed-shell)!"
                    )
            except AttributeError:
                raise ValueError(
                    "electron_type must be 'alpha' or 'beta' (open-shell), or None (closed-shell)!"
                )

        for entry in d:
            key = prefix + entry
            if d[entry][0] is not None or d[entry][1] is not None:
                crit[key] = dict()

            if d[entry][0] is not None:
                crit[key]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[key]["$lte"] = d[entry][1]

        if lp_type is not None:
            crit[prefix + "type_code"] = lp_type

        return {"criteria": crit}

    def ensure_indexes(self):
        prefixes = ["nbo_lone_pairs.", "alpha_lone_pairs.", "beta_lone_pairs."]
        keys = [
            "s_character",
            "p_character",
            "d_character",
            "f_character",
            "occupancy",
            "type_code",
        ]
        indices = list()
        for p in prefixes:
            for k in keys:
                indices.append((p + k, False))
        return indices


class NBOBondQuery(QueryOperator):
    """
    Method to generate a query on NBO bond data.
    """

    def query(
        self,
        electron_type_bond: Optional[str] = Query(
            None,
            description="Should alpha ('alpha'), beta ('beta'), or all electrons be considered (None; default)?",
        ),
        bond_type: Optional[str] = Query(
            None,
            description="Type of orbital, e.g. 'BD' for bonding or 'BD*' for antibonding",
        ),
        min_s_character_atom1: Optional[float] = Query(
            None,
            description="Minimum percentage of the bond constituted by s atomic orbitals on the first atom.",
        ),
        max_s_character_atom1: Optional[float] = Query(
            None,
            description="Maximum percentage of the bond constituted by s atomic orbitals on the first atom.",
        ),
        min_s_character_atom2: Optional[float] = Query(
            None,
            description="Minimum percentage of the bond constituted by s atomic orbitals on the second atom.",
        ),
        max_s_character_atom2: Optional[float] = Query(
            None,
            description="Maximum percentage of the bond constituted by s atomic orbitals on the second atom.",
        ),
        min_p_character_atom1: Optional[float] = Query(
            None,
            description="Minimum percentage of the bond constituted by p atomic orbitals on the first atom.",
        ),
        max_p_character_atom1: Optional[float] = Query(
            None,
            description="Maximum percentage of the bond constituted by p atomic orbitals on the first atom.",
        ),
        min_p_character_atom2: Optional[float] = Query(
            None,
            description="Minimum percentage of the bond constituted by p atomic orbitals on the second atom.",
        ),
        max_p_character_atom2: Optional[float] = Query(
            None,
            description="Maximum percentage of the bond constituted by p atomic orbitals on the second atom.",
        ),
        min_d_character_atom1: Optional[float] = Query(
            None,
            description="Minimum percentage of the bond constituted by d atomic orbitals on the first atom.",
        ),
        max_d_character_atom1: Optional[float] = Query(
            None,
            description="Maximum percentage of the bond constituted by d atomic orbitals on the first atom.",
        ),
        min_d_character_atom2: Optional[float] = Query(
            None,
            description="Minimum percentage of the bond constituted by d atomic orbitals on the second atom.",
        ),
        max_d_character_atom2: Optional[float] = Query(
            None,
            description="Maximum percentage of the bond constituted by d atomic orbitals on the second atom.",
        ),
        min_f_character_atom1: Optional[float] = Query(
            None,
            description="Minimum percentage of the bond constituted by f atomic orbitals on the first atom.",
        ),
        max_f_character_atom1: Optional[float] = Query(
            None,
            description="Maximum percentage of the bond constituted by f atomic orbitals on the first atom.",
        ),
        min_f_character_atom2: Optional[float] = Query(
            None,
            description="Minimum percentage of the bond constituted by f atomic orbitals on the second atom.",
        ),
        max_f_character_atom2: Optional[float] = Query(
            None,
            description="Maximum percentage of the bond constituted by f atomic orbitals on the second atom.",
        ),
        min_polarization_atom1: Optional[float] = Query(
            None,
            description="Minimum fraction of electrons in the bond donated by the first atom.",
        ),
        max_polarization_atom1: Optional[float] = Query(
            None,
            description="Maximum fraction of electrons in the bond donated by the first atom.",
        ),
        min_polarization_atom2: Optional[float] = Query(
            None,
            description="Minimum fraction of electrons in the bond donated by the second atom.",
        ),
        max_polarization_atom2: Optional[float] = Query(
            None,
            description="Maximum fraction of electrons in the bond donated by the second atom.",
        ),
        min_bond_occupancy: Optional[float] = Query(
            None, description="Minimum number of electrons in the bond."
        ),
        max_bond_occupancy: Optional[float] = Query(
            None, description="Maximum number of electrons in the bond."
        ),
    ) -> STORE_PARAMS:
        crit: Dict[str, Any] = dict()  # type: ignore

        d = {
            "atom1_s_character": [min_s_character_atom1, max_s_character_atom1],
            "atom1_p_character": [min_p_character_atom1, max_p_character_atom1],
            "atom1_d_character": [min_d_character_atom1, max_d_character_atom1],
            "atom1_f_character": [min_f_character_atom1, max_f_character_atom1],
            "atom2_s_character": [min_s_character_atom2, max_s_character_atom2],
            "atom2_p_character": [min_p_character_atom2, max_p_character_atom2],
            "atom2_d_character": [min_d_character_atom2, max_d_character_atom2],
            "atom2_f_character": [min_f_character_atom2, max_f_character_atom2],
            "atom1_polarization": [min_polarization_atom1, max_polarization_atom1],
            "atom2_polarization": [min_polarization_atom2, max_polarization_atom2],
            "occupancy": [min_bond_occupancy, max_bond_occupancy],
        }

        if electron_type_bond is None:
            prefix = "nbo_bonds."
        else:
            try:
                if electron_type_bond.lower() == "alpha":
                    prefix = "alpha_bonds."
                elif electron_type_bond.lower() == "beta":
                    prefix = "beta_bonds."
                else:
                    raise ValueError(
                        "electron_type must be 'alpha' or 'beta' (open-shell), or None (closed-shell)!"
                    )
            except AttributeError:
                raise ValueError(
                    "electron_type must be 'alpha' or 'beta' (open-shell), or None (closed-shell)!"
                )

        for entry in d:
            key = prefix + entry
            if d[entry][0] is not None or d[entry][1] is not None:
                crit[key] = dict()

            if d[entry][0] is not None:
                crit[key]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[key]["$lte"] = d[entry][1]

        if bond_type is not None:
            crit[prefix + "type_code"] = bond_type

        return {"criteria": crit}

    def ensure_indexes(self):
        prefixes = ["nbo_bonds.", "alpha_bonds.", "beta_bonds."]
        keys = [
            "atom1_s_character",
            "atom2_s_character",
            "atom1_p_character",
            "atom2_p_character",
            "atom1_d_character",
            "atom2_d_character",
            "atom1_f_character",
            "atom2_f_character",
            "atom1_polarization",
            "atom2_polarization",
            "occupancy",
            "type_code",
        ]
        indices = list()
        for p in prefixes:
            for k in keys:
                indices.append((p + k, False))
        return indices


class NBOInteractionQuery(QueryOperator):
    """Method to generate a query on NBO orbital-orbital interaction data"""

    def query(
        self,
        electron_type_interaction: Optional[str] = Query(
            None,
            description="Should alpha ('alpha'), beta ('beta'), or all electrons be considered (None; default)?",
        ),
        donor_type: Optional[str] = Query(
            None,
            description="Type of donor orbital, e.g. 'BD' for bonding or 'RY*' for anti-Rydberg",
        ),
        acceptor_type: Optional[str] = Query(
            None,
            description="Type of acceptor orbital, e.g. 'BD' for bonding or 'RY*' for anti-Rydberg",
        ),
        min_perturbation_energy: Optional[float] = Query(
            None, description="Minimum perturbation energy of the interaction"
        ),
        max_perturbation_energy: Optional[float] = Query(
            None, description="Maximum perturbation energy of the interaction"
        ),
        min_energy_difference: Optional[float] = Query(
            None, description="Minimum energy difference between interacting orbitals"
        ),
        max_energy_difference: Optional[float] = Query(
            None, description="Minimum energy difference between interacting orbitals"
        ),
        min_fock_element: Optional[float] = Query(
            None, description="Minimum interaction Fock matrix element"
        ),
        max_fock_element: Optional[float] = Query(
            None, description="Maximum interaction Fock matrix element"
        ),
    ) -> STORE_PARAMS:
        crit: Dict[str, Any] = dict()  # type: ignore

        d = {
            "perturbation_energy": [min_perturbation_energy, max_perturbation_energy],
            "energy_difference": [min_energy_difference, max_energy_difference],
            "fock_element": [min_fock_element, max_fock_element],
        }

        if electron_type_interaction is None:
            prefix = "nbo_interactions."
        else:
            try:
                if electron_type_interaction.lower() == "alpha":
                    prefix = "alpha_interactions."
                elif electron_type_interaction.lower() == "beta":
                    prefix = "beta_interactions."
                else:
                    raise ValueError(
                        "electron_type must be 'alpha' or 'beta' (open-shell), or None (closed-shell)!"
                    )
            except AttributeError:
                raise ValueError(
                    "electron_type must be 'alpha' or 'beta' (open-shell), or None (closed-shell)!"
                )

        for entry in d:
            key = prefix + entry
            if d[entry][0] is not None or d[entry][1] is not None:
                crit[key] = dict()

            if d[entry][0] is not None:
                crit[key]["$gte"] = d[entry][0]

            if d[entry][1] is not None:
                crit[key]["$lte"] = d[entry][1]

        if donor_type is not None:
            crit[prefix + "donor_type"] = donor_type
        if acceptor_type is not None:
            crit[prefix + "acceptor_type"] = acceptor_type

        return {"criteria": crit}

    def ensure_indexes(self):
        prefixes = ["nbo_interactions.", "alpha_interactions.", "beta_interactions."]
        keys = [
            "donor_type",
            "acceptor_type",
            "perturbation_energy",
            "energy_difference",
            "fock_element",
        ]
        indices = list()
        for p in prefixes:
            for k in keys:
                indices.append((p + k, False))
        return indices
