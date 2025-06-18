from datetime import datetime
from typing import List, Union, Dict, Tuple, Sequence, Optional

from pydantic import Field
import numpy as np
import copy
import logging
from emmet.core.base import EmmetBaseModel
from emmet.core.vasp.task_valid import TaskState
from emmet.core.neb import NebPathwayResult
from pymatgen.core import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from pymatgen.analysis.diffusion.utils.edge_data_from_sc import add_edge_data_from_sc

try:
    from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
    from pymatgen.analysis.diffusion.utils.supercells import (
        get_sc_fromstruct,
        get_start_end_structures,
    )
except ImportError:
    raise ImportError("Install pymatgen-analysis-diffusion to use MigrationGraphDoc")


class MigrationGraphDoc(EmmetBaseModel):
    """
    MigrationGraph Doc.
    Stores MigrationGraph and info such as ComputedStructureEntries (ComputedEntry can be used for working ion)
    and cutoff distance that are used to generated the object.

    Note: this doc is not self-contained within pymatgen, as it has dependence on pymatgen.analysis.diffusion,
    a namespace package aka pymatgen-diffusion.
    """

    battery_id: str = Field(
        ..., description="The battery id for this MigrationGraphDoc"
    )

    last_updated: Optional[datetime] = Field(
        None,
        description="Timestamp for the most recent calculation for this MigrationGraph document.",
    )

    warnings: Sequence[str] = Field(
        [], description="Any warnings related to this property."
    )

    deprecated: bool = Field(
        False,
        description="Indicates whether a migration graph fails to be constructed from the provided entries. Defaults to False, indicating mg can be constructed from entries.",  # noqa: E501
    )

    hop_cutoff: Optional[float] = Field(
        None,
        description="The numerical value in angstroms used to cap the maximum length of a hop.",
    )

    entries_for_generation: Optional[List[ComputedStructureEntry]] = Field(
        None,
        description="A list of ComputedStructureEntries used to generate the structure with all working ion sites.",
    )

    working_ion_entry: Optional[Union[ComputedEntry, ComputedStructureEntry]] = Field(
        None, description="The ComputedStructureEntry of the working ion."
    )

    migration_graph: Optional[MigrationGraph] = Field(
        None,
        description="The MigrationGraph object as defined in pymatgen.analysis.diffusion.",
    )

    populate_sc_fields: bool = Field(
        True,
        description="Flag indicating whether this document has populated the supercell fields",
    )

    sc_gen_schema: Optional[str] = Field(
        None,
        description="The schema used to generate supercell fields. "
        "hops_only: contains only endpoints for sc hops; complete: contains all transformed uc sites.",
    )

    min_length_sc: Optional[float] = Field(
        None,
        description="The minimum length used to generate supercell using pymatgen.",
    )

    minmax_num_atoms: Optional[Tuple[int, int]] = Field(
        None,
        description="The min/max number of atoms used to genreate supercell using pymatgen.",
    )

    matrix_supercell_structure: Optional[Structure] = Field(
        None,
        description="The matrix suprcell structure that does not contain the mobile ions for the purpose of migration analysis.",  # noqa: E501
    )

    conversion_matrix: Optional[List[List[Union[int, float]]]] = Field(
        None,
        description="The conversion matrix used to convert unit cell to supercell.",
    )

    inserted_ion_coords: Optional[
        List[Dict[str, Union[List[float], str, int]]]
    ] = Field(
        None,
        description="A dictionary containing all mobile ion fractional coordinates in terms of supercell.",
    )

    insert_coords_combo: Optional[List[str]] = Field(
        None,
        description="A list of combinations 'a+b' to designate hops in the supercell. Each combo should correspond to one unique hop in MigrationGraph.",  # noqa: E501
    )

    paths_summary: Optional[Dict[int, List]] = Field(
        None,
        description="A dictionary of ranked intercalation pathways given cost (e.g. migration barrier from transition state calcs) of each unique_hop.",  # noqa: E501
    )

    migration_graph_w_cost: Optional[MigrationGraph] = Field(
        None,
        description="MigrationGraph instance that contains cost (e.g. from NEB) information",
    )

    @classmethod
    def from_entries_and_distance(
        cls,
        battery_id: str,
        grouped_entries: List[ComputedStructureEntry],
        working_ion_entry: Union[ComputedEntry, ComputedStructureEntry],
        hop_cutoff: float,
        populate_sc_fields: bool = True,
        sc_gen_schema: str = "complete",
        ltol: float = 0.2,
        stol: float = 0.3,
        angle_tol: float = 5,
        **kwargs,
    ) -> Union["MigrationGraphDoc", None]:
        """
        This classmethod takes a group of ComputedStructureEntries (can also use ComputedEntry for wi) and generates
        a full sites structure.
        Then a MigrationGraph object is generated with with_distance() method with a designated cutoff.
        If populate_sc_fields set to True, this method will populate the supercell related fields. Required kwargs are
        min_length_sc and minmax_num_atoms.
        """

        ranked_structures = MigrationGraph.get_structure_from_entries(
            entries=grouped_entries, migrating_ion_entry=working_ion_entry
        )
        max_sites_struct = ranked_structures[0]

        migration_graph = MigrationGraph.with_distance(
            structure=max_sites_struct,
            migrating_specie=working_ion_entry.composition.chemical_system,
            max_distance=hop_cutoff,
        )

        if not populate_sc_fields:
            return cls(
                battery_id=battery_id,
                hop_cutoff=hop_cutoff,
                entries_for_generation=grouped_entries,
                working_ion_entry=working_ion_entry,
                migration_graph=migration_graph,
                **kwargs,
            )

        else:
            if all(arg in kwargs for arg in ["min_length_sc", "minmax_num_atoms"]):
                sm = StructureMatcher(ltol, stol, angle_tol)
                (
                    host_sc,
                    sc_mat,
                    min_length_sc,
                    minmax_num_atoms,
                    coords_list,
                    combo,
                ) = cls.generate_sc_fields(
                    mg=migration_graph,
                    min_length_sc=kwargs["min_length_sc"],
                    minmax_num_atoms=kwargs["minmax_num_atoms"],
                    sm=sm,
                    sc_gen_schema=sc_gen_schema,
                )

                return cls(
                    battery_id=battery_id,
                    hop_cutoff=hop_cutoff,
                    entries_for_generation=grouped_entries,
                    working_ion_entry=working_ion_entry,
                    migration_graph=migration_graph,
                    matrix_supercell_structure=host_sc,
                    conversion_matrix=sc_mat,
                    inserted_ion_coords=coords_list,
                    insert_coords_combo=combo,
                    sc_gen_schema=sc_gen_schema,
                    **kwargs,
                )

            else:
                raise TypeError(
                    "Please make sure to have kwargs min_length_sc and minmax_num_atoms if populate_sc_fields is set to True."  # noqa: E501
                )

    @classmethod
    def augment_from_mgd_and_npr(
        cls,
        mgd: "MigrationGraphDoc",
        npr: NebPathwayResult,
        barrier_type: str,
    ) -> "MigrationGraphDoc":
        """
        This class method takes an existing MigrationGraphDoc and augments it by populating
        the paths_summary and migration_graph_w_cost fields with transition state data from
        NebPathwayResult.

        barrier_type can be set to 'barrier' or 'energy_range'.
        See docstring of get_paths_summary_with_neb_res for detail.
        """
        mgd_w_cost = copy.deepcopy(mgd)
        paths_summary, mg_new = cls.get_paths_summary_with_neb_res(
            mg=mgd_w_cost.migration_graph, npr=npr, barrier_type=barrier_type
        )
        mgd_w_cost.paths_summary = paths_summary
        mgd_w_cost.migration_graph_w_cost = mg_new
        return mgd_w_cost

    @staticmethod
    def generate_sc_fields(
        mg: MigrationGraph,
        min_length_sc: float,
        minmax_num_atoms: Tuple[int, int],
        sm: StructureMatcher,
        sc_gen_schema: str,
    ):
        if sc_gen_schema not in ["hops_only", "complete"]:
            raise ValueError(
                f"Invalid sc_gen_schema: {sc_gen_schema}. Specify 'hops_only' or 'complete'."
            )

        min_length_sc = min_length_sc
        minmax_num_atoms = minmax_num_atoms

        sc_mat = get_sc_fromstruct(
            base_struct=mg.structure,
            min_atoms=minmax_num_atoms[0],
            max_atoms=minmax_num_atoms[1],
            min_length=min_length_sc,
        )

        sc_mat = sc_mat.tolist()  # type: ignore[attr-defined]
        host_sc = mg.host_structure * sc_mat
        working_ion = mg.only_sites[0].species_string

        if sc_gen_schema == "hops_only":
            coords_list, combo = MigrationGraphDoc.get_sc_info_hops_only(mg, sc_mat)

        if sc_gen_schema == "complete":
            coords_list = MigrationGraphDoc.ordered_sc_site_list(mg.only_sites, sc_mat)
            combo, coords_list = MigrationGraphDoc.get_hop_sc_combo(
                mg.unique_hops, sc_mat, sm, host_sc, working_ion, coords_list
            )

        return host_sc, sc_mat, min_length_sc, minmax_num_atoms, coords_list, combo

    @staticmethod
    def get_sc_info_hops_only(mg: MigrationGraph, sc_mat: list[list[int | float]]):
        coords_list = []
        combo = []
        base_struct = mg.host_structure

        for one_hop in mg.unique_hops.values():
            migration_hop = one_hop["hop"]
            isite, iindex = migration_hop.isite, one_hop["iindex"]
            esite, eindex = migration_hop.esite, one_hop["eindex"]
            start_structure, end_structure, _ = get_start_end_structures(
                isite=isite,
                esite=esite,
                base_struct=base_struct,
                sc_mat=sc_mat,
                vac_mode=False,
            )

            sc_ini_info = {
                "uc_site_type": iindex,
                "site_frac_coords": tuple(start_structure[0].frac_coords),
            }
            if sc_ini_info not in coords_list:
                coords_list.append(sc_ini_info)
            combo_ini = coords_list.index(sc_ini_info)

            sc_fin_info = {
                "uc_site_type": eindex,
                "site_frac_coords": tuple(end_structure[0].frac_coords),
            }
            if sc_fin_info not in coords_list:
                coords_list.append(sc_fin_info)
            combo_fin = coords_list.index(sc_fin_info)

            combo.append(f"{combo_ini}+{combo_fin}")

        for coords in coords_list:
            coords["site_frac_coords"] = list(coords["site_frac_coords"])

        return coords_list, combo

    @staticmethod
    def ordered_sc_site_list(uc_sites_only: Structure, sc_mat: List[List[int]]):
        uc_no_site = uc_sites_only.copy()
        uc_no_site.remove_sites(range(len(uc_sites_only)))
        working_ion = uc_sites_only[0].species_string
        sc_site_dict = {}  # type: dict

        for i, e in enumerate(uc_sites_only):
            uc_one_set = uc_no_site.copy()
            uc_one_set.insert(0, working_ion, e.frac_coords)
            sc_one_set = uc_one_set * sc_mat
            for index in range(len(sc_one_set)):
                sc_site_dict[len(sc_site_dict) + 1] = {
                    "uc_site_type": i,
                    "site_frac_coords": list(sc_one_set[index].frac_coords),
                    # "extra_site": False
                }

        ordered_site_list = [
            e
            for i, e in enumerate(
                sorted(
                    sc_site_dict.values(),
                    key=lambda v: float(np.linalg.norm(v["site_frac_coords"])),
                )
            )
        ]
        return ordered_site_list

    @staticmethod
    def get_hop_sc_combo(
        unique_hops: Dict,
        sc_mat: List[List[int]],
        sm: StructureMatcher,
        host_sc: Structure,
        working_ion: str,
        ordered_sc_site_list: list,
    ):
        combo = []

        unique_hops = {k: v for k, v in sorted(unique_hops.items())}
        for one_hop in unique_hops.values():
            added = False
            sc_isite_set = {
                k: v
                for k, v in enumerate(ordered_sc_site_list)
                if v["uc_site_type"] == one_hop["iindex"]
            }
            sc_esite_set = {
                k: v
                for k, v in enumerate(ordered_sc_site_list)
                if v["uc_site_type"] == one_hop["eindex"]
            }
            for sc_iindex, sc_isite in sc_isite_set.items():
                for sc_eindex, sc_esite in sc_esite_set.items():
                    sc_check = host_sc.copy()
                    sc_check.insert(0, working_ion, sc_isite["site_frac_coords"])
                    sc_check.insert(1, working_ion, sc_esite["site_frac_coords"])
                    if MigrationGraphDoc.compare_sc_one_hop(
                        one_hop,
                        sc_mat,
                        sm,
                        host_sc,
                        sc_check,
                        working_ion,
                        (sc_isite["uc_site_type"], sc_esite["uc_site_type"]),
                    ):
                        combo.append(f"{sc_iindex}+{sc_eindex}")
                        added = True
                        break
                if added:
                    break

            if not added:
                new_combo, ordered_sc_site_list = MigrationGraphDoc.append_new_site(
                    host_sc, ordered_sc_site_list, one_hop, sc_mat, working_ion
                )
                combo.append(new_combo)

        return combo, ordered_sc_site_list

    @staticmethod
    def compare_sc_one_hop(
        one_hop: Dict,
        sc_mat: List,
        sm: StructureMatcher,
        host_sc: Structure,
        sc_check: Structure,
        working_ion: str,
        uc_site_types: Tuple[int, int],
    ):
        sc_mat_inv = np.linalg.inv(sc_mat)
        convert_sc_icoords = np.dot(one_hop["ipos"], sc_mat_inv)
        convert_sc_ecoords = np.dot(one_hop["epos"], sc_mat_inv)
        convert_sc = host_sc.copy()
        convert_sc.insert(0, working_ion, convert_sc_icoords)
        convert_sc.insert(1, working_ion, convert_sc_ecoords)

        if sm.fit(convert_sc, sc_check):
            one_hop_dis = one_hop["hop"].length
            sc_check_hop_dis = np.linalg.norm(sc_check[0].coords - sc_check[1].coords)
            if np.isclose(one_hop_dis, sc_check_hop_dis, atol=1e-5):
                if (
                    one_hop["iindex"] == uc_site_types[0]
                    and one_hop["eindex"] == uc_site_types[1]
                ):
                    return True

        return False

    @staticmethod
    def append_new_site(
        host_sc: Structure,
        ordered_sc_site_list: list,
        one_hop: Dict,
        sc_mat: List[List[int]],
        working_ion: str,
    ):
        sc_mat_inv = np.linalg.inv(sc_mat)
        sc_ipos = np.dot(one_hop["ipos"], sc_mat_inv)
        sc_epos = np.dot(one_hop["epos"], sc_mat_inv)
        sc_iindex, sc_eindex = None, None
        host_sc_insert = host_sc.copy()

        for k, v in enumerate(ordered_sc_site_list):
            if np.allclose(sc_ipos, v["site_frac_coords"], rtol=0.1, atol=0.1):
                sc_iindex = k
            if np.allclose(sc_epos, v["site_frac_coords"], rtol=0.1, atol=0.1):
                sc_eindex = k

        if sc_iindex is None:
            host_sc_insert.insert(0, working_ion, sc_ipos)
            ordered_sc_site_list.append(
                {
                    "uc_site_type": one_hop["iindex"],
                    "site_frac_coords": list(host_sc_insert[0].frac_coords),
                    "extra_site": True,
                }
            )
            sc_iindex = len(ordered_sc_site_list) - 1
        if sc_eindex is None:
            host_sc_insert.insert(0, working_ion, sc_epos)
            ordered_sc_site_list.append(
                {
                    "uc_site_type": one_hop["eindex"],
                    "site_frac_coords": list(host_sc_insert[0].frac_coords),
                    "extra_site": True,
                }
            )
            sc_eindex = len(ordered_sc_site_list) - 1

        return f"{sc_iindex}+{sc_eindex}", ordered_sc_site_list

    @staticmethod
    def get_distinct_hop_sites(
        inserted_ion_coords: List[str], insert_coords_combo: List
    ) -> Tuple[List, List[str], Dict]:
        """
        This is a utils function that converts the site dict and combo into a site list and combo that contain only distince endpoints used the combos. # noqa: E501
        """
        dis_sites_list = []
        dis_combo_list = []
        mgdoc_sites_mapping = {}  # type: dict
        combo_mapping = {}

        for one_combo in insert_coords_combo:
            ini, end = list(map(int, one_combo.split("+")))

            if ini in mgdoc_sites_mapping.keys():
                dis_ini = mgdoc_sites_mapping[ini]
            else:
                dis_sites_list.append(list(inserted_ion_coords[ini]["site_frac_coords"]))  # type: ignore
                dis_ini = len(dis_sites_list) - 1
                mgdoc_sites_mapping[ini] = dis_ini
            if end in mgdoc_sites_mapping.keys():
                dis_end = mgdoc_sites_mapping[end]
            else:
                dis_sites_list.append(list(inserted_ion_coords[end]["site_frac_coords"]))  # type: ignore
                dis_end = len(dis_sites_list) - 1
                mgdoc_sites_mapping[end] = dis_end

            dis_combo = f"{dis_ini}+{dis_end}"
            dis_combo_list.append(dis_combo)
            combo_mapping[dis_combo] = one_combo

        return dis_sites_list, dis_combo_list, combo_mapping

    @staticmethod
    def get_paths_summary_with_neb_res(
        mg: MigrationGraph,
        npr: NebPathwayResult,
        barrier_type: str,
        zero_short_hop_cost: bool = True,
    ) -> Tuple[Dict[int, List], MigrationGraph]:
        """
        This is a post-processing function that matches the results of transition state cals (NEB or ApproxNEB)
        and unique_hops in the MigrationGraph, and then outputs a ranked list according to the calculated barrier

        Parameters
        ----------
        mgd: MigrationGraph
            The MigrationGraph to be matched and get paths from
        npr: NebPathwayResult
            The doc used to get transition state calc info
        barrier_type: str
            The type of barrier used to assign cost. Currently supporting
            'barrier': max of forward & reverse barrier (max energy - ep energy)
            'energy_range': max of energies - min of energies
        """
        if not barrier_type or barrier_type not in ["max_barrier", "energy_range"]:
            raise ValueError(
                f"Invalid barrier_type: {barrier_type}. Specify 'max_barrier' or 'energy_range'."
            )

        energy_struct_info = MigrationGraphDoc._get_energy_struct_info(npr)
        mg_new = copy.deepcopy(mg)

        for info in energy_struct_info.values():
            try:
                add_edge_data_from_sc(
                    mg_new,
                    i_sc=info["input_endpoints"][0],
                    e_sc=info["input_endpoints"][-1],
                    data_array=info,
                    key="energy_struct_info",
                )
            except (RuntimeError, ValueError) as e:
                logging.warning(f"{e} occured to during matching")

        unmatched_uhops = []
        failed_neb_uhops = []

        for k, v in mg_new.unique_hops.items():
            # if a unique_hop failed to match with an NEB hops calc (no symmetry match, missing calc, etc.)
            # the cost is set to infinity.
            # if a unique_hops matches to an NEB hop in the FAILED state
            # cost is set to the insertion energy diff (barrier from NebResult)
            # but the failed state is explicitly stated in paths_summary
            if "energy_struct_info" not in v:
                cost, hop_key, state = float("inf"), "", "unmatched"
                unmatched_uhops.append(k)
            else:
                state = v["energy_struct_info"]["state"]
                if state == TaskState.FAILED:
                    failed_neb_uhops.append(k)
                cost, hop_key = (
                    v["energy_struct_info"][barrier_type],
                    v["energy_struct_info"]["hop_key"],
                )
                # for short hops with low barrier, set cost to 0
                if zero_short_hop_cost:
                    cutoff = 2 * MigrationGraphDoc._get_wi_ionic_radius(mg_new)
                    if MigrationGraphDoc._check_short_hop(
                        v, current_cost=cost, length_cutoff=cutoff
                    ):
                        cost = 0
            mg_new.add_data_to_similar_edges(
                target_label=v["hop_label"],
                data={"cost": cost, "hop_key": hop_key, "match_state": state},
            )

        logging.warning(
            f"The following unique hops have not matched: {unmatched_uhops}"
        )
        logging.warning(
            f"The following unique_hops matched but the corresponding calculation "
            f"is in the FAILED state: {failed_neb_uhops}"
        )

        paths = list(mg_new.get_path())
        paths_summary = {}
        for one_path in paths:
            path_summary = []
            for one_hop in one_path[1]:
                hop_summary = {
                    key: value
                    for key, value in one_hop.items()
                    if key
                    in ["hop_label", "hop_key", "hop_distance", "cost", "match_state"]
                }
                path_summary.append(hop_summary)
            paths_summary[one_path[0]] = path_summary

        return paths_summary, mg_new

    @staticmethod
    def _get_energy_struct_info(npr: NebPathwayResult) -> Dict:
        """
        This is a helper function that converts results in NebPathWayResult into
        an info dict to be inserted into unique_hops of MigrationGraph
        """
        energy_struct_info = {}
        for hop_key, data in npr.hops.items():
            energy_struct_info[hop_key] = {
                "hop_key": hop_key,
                "max_barrier": npr.max_barriers[hop_key],
                "energy_range": data.barrier_energy_range,
                "energies": data.energies,
                "state": data.state,
                "calc_fail_info": data.failure_reasons,
                "input_endpoints": [data.initial_images[0], data.initial_images[-1]],
                "output_structs": data.images,
            }
        return energy_struct_info

    @staticmethod
    def _get_wi_ionic_radius(mg: MigrationGraph):
        wi = mg.only_sites[0].specie
        wi_oxi_state_guess = mg.structure.composition.oxi_state_guesses()[0][wi.name]
        if wi_oxi_state_guess in wi.ionic_radii:
            return wi.ionic_radii[wi_oxi_state_guess]
        return wi.ionic_radii[min(wi.ionic_radii)]

    @staticmethod
    def _check_short_hop(
        unique_hop: dict,
        current_cost: float,
        length_cutoff: float,
        barrier_cutoff: float = 0.02,
    ):
        hop_length = unique_hop["hop_distance"]
        if hop_length < length_cutoff and current_cost < barrier_cutoff:
            return True
        return False
