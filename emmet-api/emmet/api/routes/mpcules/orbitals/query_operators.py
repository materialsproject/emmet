# from typing import Optional
# from fastapi import Query
# from maggma.api.query_operator import QueryOperator
# from maggma.api.utils import STORE_PARAMS


# class NBOPopulationQuery(QueryOperator):
#     """
#     Method to generate a query on NBO natural population data.
#     """

#     def query(
#         self,
#         open_shell: Optional[bool] = Query(
#             False,
#             description="Should the molecules have unpaired (radical) electrons?"
#         ),
#         electron_type: Optional[str] = Query(
#             None,
#             description="Should alpha ('alpha'), beta ('beta'), or all electrons be considered (None; default)?"
#         ),
#         min_core_electron: Optional[float] = Query(
#             None,
#             description="Minimum number of core electrons in an atom in this molecule."
#         ),
#         max_core_electron: Optional[float] = Query(
#             None,
#             description="Maximum number of core electrons in an atom in this molecule."
#         ),
#         min_valence_electron: Optional[float] = Query(
#             None,
#             description="Minimum number of valence electrons in an atom in this molecule."
#         ),
#         max_valence_electron: Optional[float] = Query(
#             None,
#             description="Maximum number of valence electrons in an atom in this molecule."
#         ),
#         min_rydberg_electron: Optional[float] = Query(
#             None,
#             description="Minimum number of Rydberg electrons in an atom in this molecule."
#         ),
#         max_rydberg_electron: Optional[float] = Query(
#             None,
#             description="Maximum number of Rydberg electrons in an atom in this molecule."
#         ),
#     ) -> STORE_PARAMS:

#         crit = {"open_shell": open_shell}

#         d = {
#             "core_electrons": [min_core_electron, max_core_electron],
#             "valence_electrons": [min_valence_electron, max_valence_electron],
#             "rydberg_electrons": [min_rydberg_electron, max_rydberg_electron],
#         }

#         if electron_type is None or not open_shell:
#             prefix = "nbo_population."
#         elif electron_type.lower() == "alpha":
#             prefix = "alpha_population."
#         elif electron_type.lower() == "beta":
#             prefix = "beta_population."
#         else:
#             raise ValueError("electron_type must be 'alpha', 'beta', or None!")

#         for entry in d:
#             key = prefix + entry
#             if d[entry][0] is not None or d[entry][1] is not None:
#                 crit[key] = dict()

#             if d[entry][0] is not None:
#                 crit[key]["$gte"] = d[entry][0]

#             if d[entry][1] is not None:
#                 crit[key]["$lte"] = d[entry][1]

#         return {"criteria": crit}

#     def ensure_indexes(self):  # pragma: no cover
#         return [("open_shell", False),
#                 ("nbo_population.core_electrons", False),
#                 ("nbo_population.valence_electrons", False),
#                 ("nbo_population.rydberg_electrons", False),
#                 ("alpha_population.core_electrons", False),
#                 ("alpha_population.valence_electrons", False),
#                 ("alpha_population.rydberg_electrons", False),
#                 ("beta_population.core_electrons", False),
#                 ("beta_population.valence_electrons", False),
#                 ("beta_population.rydberg_electrons", False)]


# class NBOLonePairQuery(BaseQuery):
#     """
#     Method to generate a query on NBO lone pair data.
#     """

#     def query(
#         self,
#         open_shell: Optional[bool] = Query(
#             False,
#             description="Should the molecules have unpaired (radical) electrons?"
#         ),
#         electron_type: Optional[str] = Query(
#             None,
#             description="Should alpha ('alpha'), beta ('beta'), or all electrons be considered (None; default)?"
#         ),
#         lp_type: Optional[str] = Query(
#             None,
#             description="Type of orbital - 'LP' for 'lone pair' or 'LV' for 'lone vacant'"
#         ),
#         min_s_character: Optional[float] = Query(
#             None,
#             description="Minimum percentage of the lone pair constituted by s atomic orbitals."
#         ),
#         max_s_character: Optional[float] = Query(
#             None,
#             description="Maximum percentage of the lone pair constituted by s atomic orbitals."
#         ),
#         min_p_character: Optional[float] = Query(
#             None,
#             description="Minimum percentage of the lone pair constituted by p atomic orbitals."
#         ),
#         max_p_character: Optional[float] = Query(
#             None,
#             description="Maximum percentage of the lone pair constituted by p atomic orbitals."
#         ),
#         min_d_character: Optional[float] = Query(
#             None,
#             description="Minimum percentage of the lone pair constituted by d atomic orbitals."
#         ),
#         max_d_character: Optional[float] = Query(
#             None,
#             description="Maximum percentage of the lone pair constituted by d atomic orbitals."
#         ),
#         min_f_character: Optional[float] = Query(
#             None,
#             description="Minimum percentage of the lone pair constituted by f atomic orbitals."
#         ),
#         max_f_character: Optional[float] = Query(
#             None,
#             description="Maximum percentage of the lone pair constituted by f atomic orbitals."
#         ),
#     ):
#         pass

#     def ensure_indexes(self):
#         prefixes = ["nbo_lone_pairs.", ""]
#         keys = [
#             ".max",
#             "bond_length_stats.min",
#             "bond_length_stats.mean",
#         ]
#         return [(key, False) for key in keys]


# class NBOBondQuery(BaseQuery):
#     pass


# class NBOInteractionQuery(BaseQuery):
#     pass
