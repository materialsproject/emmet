from typing import Tuple, List, Dict
from emmet.core.mobility.migrationgraph import MigrationGraphDoc


def get_aneb_wf_inputs(
    mgdoc: MigrationGraphDoc
) -> Tuple[List, List[str], Dict]:
    """
    This is a utils function that takes a MigrationGraphDoc object and converts the site dict and combo into inputs for aneb wf on atomate (compatibility for atomate2 to come).
    Using the results of this function as inputs for atomate's aneb wf will avoid unnecessary enpoint calculations, since MGDoc's site dict contains sites that are not used in sites combo.
    """
    if mgdoc.inserted_ion_coords is None or mgdoc.insert_coords_combo is None:
        raise TypeError("Please make sure that the MGDoc passed in has inserted_ion_coords and inserted_coords_combo fields filled.")

    else:
        anebwf_sites_list = []
        aneb_combo_list = []
        mgdoc_sites_mapping = {}  # type: dict
        combo_mapping = {}

        for one_combo in mgdoc.insert_coords_combo:
            ini, end = list(map(int, one_combo.split("+")))

            if ini in mgdoc_sites_mapping.keys():
                aneb_ini = mgdoc_sites_mapping[ini]
            else:
                anebwf_sites_list.append(list(mgdoc.inserted_ion_coords[ini]["site"].frac_coords))
                aneb_ini = len(anebwf_sites_list) - 1
                mgdoc_sites_mapping[ini] = aneb_ini
            if end in mgdoc_sites_mapping.keys():
                aneb_end = mgdoc_sites_mapping[end]
            else:
                anebwf_sites_list.append(list(mgdoc.inserted_ion_coords[end]["site"].frac_coords))
                aneb_end = len(anebwf_sites_list) - 1
                mgdoc_sites_mapping[end] = aneb_end

            aneb_combo = f"{aneb_ini}+{aneb_end}"
            aneb_combo_list.append(aneb_combo)
            combo_mapping[aneb_combo] = one_combo

        return anebwf_sites_list, aneb_combo_list, combo_mapping
