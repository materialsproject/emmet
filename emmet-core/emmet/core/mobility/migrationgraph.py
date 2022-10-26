from datetime import datetime
from typing import List, Union, Dict, Tuple, Sequence

from pydantic import Field
import numpy as np
from emmet.core.base import EmmetBaseModel
from pymatgen.core import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

try:
    from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
    from pymatgen.analysis.diffusion.utils.supercells import get_sc_fromstruct
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

    battery_id: str = Field(..., description="The battery id for this MigrationGraphDoc")

    last_updated: datetime = Field(
        None, description="Timestamp for the most recent calculation for this MigrationGraph document.",
    )

    warnings: Sequence[str] = Field([], description="Any warnings related to this property.")

    deprecated: bool = Field(
        False,
        description="Indicates whether a migration graph fails to be constructed from the provided entries. Defaults to False, indicating mg can be constructed from entries.",  # noqa: E501
    )

    hop_cutoff: float = Field(
        None, description="The numerical value in angstroms used to cap the maximum length of a hop.",
    )

    entries_for_generation: List[ComputedStructureEntry] = Field(
        None,
        description="A list of ComputedStructureEntries used to generate the structure with all working ion sites.",
    )

    working_ion_entry: Union[ComputedEntry, ComputedStructureEntry] = Field(
        None, description="The ComputedStructureEntry of the working ion."
    )

    migration_graph: MigrationGraph = Field(
        None, description="The MigrationGraph object as defined in pymatgen.analysis.diffusion.",
    )

    populate_sc_fields: bool = Field(
        True, description="Flag indicating whether this document has populated the supercell fields",
    )

    min_length_sc: float = Field(
        None, description="The minimum length used to generate supercell using pymatgen.",
    )

    minmax_num_atoms: Tuple[int, int] = Field(
        None, description="The min/max number of atoms used to genreate supercell using pymatgen.",
    )

    matrix_supercell_structure: Structure = Field(
        None,
        description="The matrix suprcell structure that does not contain the mobile ions for the purpose of migration analysis.",  # noqa: E501
    )

    conversion_matrix: List[List[Union[int, float]]] = Field(
        None, description="The conversion matrix used to convert unit cell to supercell.",
    )

    inserted_ion_coords: List[Dict[str, Union[List[float], str, int]]] = Field(
        None, description="A dictionary containing all mobile ion fractional coordinates in terms of supercell.",
    )

    insert_coords_combo: List[str] = Field(
        None,
        description="A list of combinations 'a+b' to designate hops in the supercell. Each combo should correspond to one unique hop in MigrationGraph.",  # noqa: E501
    )

    @classmethod
    def from_entries_and_distance(
        cls,
        battery_id: str,
        grouped_entries: List[ComputedStructureEntry],
        working_ion_entry: Union[ComputedEntry, ComputedStructureEntry],
        hop_cutoff: float,
        populate_sc_fields: bool = True,
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
                ) = MigrationGraphDoc.generate_sc_fields(
                    mg=migration_graph,
                    min_length_sc=kwargs["min_length_sc"],
                    minmax_num_atoms=kwargs["minmax_num_atoms"],
                    sm=sm,
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
                    **kwargs,
                )

            else:
                raise TypeError(
                    "Please make sure to have kwargs min_length_sc and minmax_num_atoms if populate_sc_fields is set to True."  # noqa: E501
                )

    @staticmethod
    def generate_sc_fields(
        mg: MigrationGraph, min_length_sc: float, minmax_num_atoms: Tuple[int, int], sm: StructureMatcher,
    ):
        min_length_sc = min_length_sc
        minmax_num_atoms = minmax_num_atoms

        sc_mat = get_sc_fromstruct(
            base_struct=mg.structure,
            min_atoms=minmax_num_atoms[0],
            max_atoms=minmax_num_atoms[1],
            min_length=min_length_sc,
        )

        sc_mat = sc_mat.tolist()
        host_sc = mg.host_structure * sc_mat
        working_ion = mg.only_sites[0].species_string

        coords_list = MigrationGraphDoc.ordered_sc_site_list(mg.only_sites, sc_mat)
        combo, coords_list = MigrationGraphDoc.get_hop_sc_combo(
            mg.unique_hops, sc_mat, sm, host_sc, working_ion, coords_list
        )

        return host_sc, sc_mat, min_length_sc, minmax_num_atoms, coords_list, combo

    @staticmethod
    def ordered_sc_site_list(uc_sites_only: Structure, sc_mat: List[List[Union[int, float]]]):
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
                sorted(sc_site_dict.values(), key=lambda v: float(np.linalg.norm(v["site_frac_coords"])),)
            )
        ]
        return ordered_site_list

    @staticmethod
    def get_hop_sc_combo(
        unique_hops: Dict,
        sc_mat: List[List[Union[int, float]]],
        sm: StructureMatcher,
        host_sc: Structure,
        working_ion: str,
        ordered_sc_site_list: list,
    ):
        combo = []

        unique_hops = {k: v for k, v in sorted(unique_hops.items())}
        for one_hop in unique_hops.values():
            added = False
            sc_isite_set = {k: v for k, v in enumerate(ordered_sc_site_list) if v["uc_site_type"] == one_hop["iindex"]}
            sc_esite_set = {k: v for k, v in enumerate(ordered_sc_site_list) if v["uc_site_type"] == one_hop["eindex"]}
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
        sc_mat: List[List[Union[int, float]]],
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

    def get_distinct_hop_sites(self) -> Tuple[List, List[str], Dict]:
        """
        This is a utils function that converts the site dict and combo into a site list and combo that contain only distince endpoints used the combos. # noqa: E501
        """
        if self.inserted_ion_coords is None or self.insert_coords_combo is None:
            raise TypeError(
                "Please make sure that the MGDoc passed in has inserted_ion_coords and inserted_coords_combo fields filled."  # noqa: E501
            )

        else:
            dis_sites_list = []
            dis_combo_list = []
            mgdoc_sites_mapping = {}  # type: dict
            combo_mapping = {}

            for one_combo in self.insert_coords_combo:
                ini, end = list(map(int, one_combo.split("+")))

                if ini in mgdoc_sites_mapping.keys():
                    dis_ini = mgdoc_sites_mapping[ini]
                else:
                    dis_sites_list.append(
                        list(self.inserted_ion_coords[ini]["site_frac_coords"])  # type: ignore
                    )
                    dis_ini = len(dis_sites_list) - 1
                    mgdoc_sites_mapping[ini] = dis_ini
                if end in mgdoc_sites_mapping.keys():
                    dis_end = mgdoc_sites_mapping[end]
                else:
                    dis_sites_list.append(
                        list(self.inserted_ion_coords[end]["site_frac_coords"])  # type: ignore
                    )
                    dis_end = len(dis_sites_list) - 1
                    mgdoc_sites_mapping[end] = dis_end

                dis_combo = f"{dis_ini}+{dis_end}"
                dis_combo_list.append(dis_combo)
                combo_mapping[dis_combo] = one_combo

            return dis_sites_list, dis_combo_list, combo_mapping
