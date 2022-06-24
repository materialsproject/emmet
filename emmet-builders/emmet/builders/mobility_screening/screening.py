import numpy as np
from itertools import chain
from pymatgen.core import Structure
from pymatgen.analysis.diffusion.utils.supercells import get_sc_fromstruct
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
from emmet.builders.mobility_screening.migration_graph_2 import MigrationGraphBuilder


def convert_unique_hops(unique_hop_dict, P_inv=None):
    # go through every unique hop to get base cell coordinates
    # and convert to supercell coordinates
    # assign end_point_combo and store results in hop_input
    bs_insert_coords, sc_insert_coords = [], []
    hop_input = dict()
    for h in unique_hop_dict.values():
        # get fractional coordinates in base structure
        i_coords = list(h["ipos"])
        e_coords = list(h["epos"])

        # put end point coordinates into a list
        # avoid duplicates to get list of unique end points
        for coords in [i_coords, e_coords]:
            if coords not in bs_insert_coords:
                bs_insert_coords.append(coords)
                if P_inv is not None:
                    sc_insert_coords.append(list(np.dot(coords, P_inv)))

        i_index = bs_insert_coords.index(i_coords)
        e_index = bs_insert_coords.index(e_coords)

        end_point_combo = str(i_index) + "+" + str(e_index)  # key to identify hops
        hop_input[end_point_combo] = {
            "hop_label": h["hop_label"],
            "hop_distance": h["hop_distance"],
            "ipos": i_coords,
            "epos": e_coords,
            "ipos_cart": h["ipos_cart"],
            "epos_cart": h["epos_cart"],
        }
    return hop_input, sc_insert_coords


def get_mobility_inputs(mg):
    # get ANEB workflow inputs from migration graph unique hops
    base = mg.host_structure.copy()
    if base.site_properties != {}:
        for p in base.site_properties.keys():
            base.remove_site_property(p)

    # get supercell structure by scaling base structure
    try:
        P = get_sc_fromstruct(base)
        P_inv = np.linalg.inv(P)
        sc_struct = base * P
        host_supercell = {
            "structure": sc_struct.as_dict(),
            "num_sites": sc_struct.num_sites,
        }
    except:
        P = None
        P_inv = None
        host_supercell = None
        # raise ValueError("Error generating supercell")

    # get hop_input from unique hops dict
    hop_input, sc_insert_coords = convert_unique_hops(mg.unique_hops, P_inv)

    # get list of all end_point_combos (one per unique hop)
    insert_coords_combinations = [k for k in hop_input.keys()]

    # get additional fields for workflow (recommended to store)
    wf_add_fields = {
        "hop_input": hop_input,
        "base_struct": base.as_dict(),
        "P": P,
        "P_inv": P_inv,
    }

    # get output doc for target store
    output = {
        "host_supercell": host_supercell,
        "supercell_insert_coords": sc_insert_coords,
        "num_insert_sites": len(
            set(chain(*[i.split("+") for i in insert_coords_combinations]))
        ),
        "insert_coords_combinations": insert_coords_combinations,
        "num_hops": len(insert_coords_combinations),
        "wf_additional_fields": wf_add_fields,
    }

    return output


class RankElectrodesBuilder(MigrationGraphBuilder):
    def get_voltage_cost(self, v, lower_x_cutoff=1.8, upper_x_cutoff=2.8, cost_trans=1):
        x_target = (lower_x_cutoff + upper_x_cutoff) / 2
        cost = cost_trans * ((v - x_target) / (lower_x_cutoff - x_target)) ** 2
        return cost

    def get_stability_cost(self, v, x_trans=0.2, cost_trans=2):
        cost = cost_trans * (2 * np.e ** (4 * (v - x_trans)) - 1)
        if cost < 0:
            cost = 0
        return cost

    def unary_function(self, item: dict) -> dict:
        out = super().unary_function(item)
        del out["task_docs"]

        # check if ICSD experimental structure
        struct = Structure.from_dict(item["host_structure"])
        mp_ids = self.mpr.find_structure(struct)
        icsd_exp = False
        icsd_ids = []
        for q in self.mpr.query(
            {"material_id": {"$in": mp_ids}}, ["theoretical", "icsd_ids"]
        ):
            if q["theoretical"] == False and len(q["icsd_ids"]) > 0:
                icsd_exp = True
                icsd_ids.extend(q["icsd_ids"])

        # calculate costs
        v_cost = self.get_voltage_cost(item["average_voltage"])
        chg_stability_cost = self.get_stability_cost(item["stability_charge"])
        dchg_stability_cost = self.get_stability_cost(item["stability_discharge"])
        cost = v_cost + chg_stability_cost + dchg_stability_cost

        # check for pathway connectivity
        if out["migration_graph"] is None:
            num_paths_found = None
            mobility_inputs = None
        else:
            num_paths_found = 0
            mg = MigrationGraph.from_dict(out["migration_graph"])
            for n, hops in mg.get_path():
                num_paths_found += 1
            mobility_inputs = get_mobility_inputs(mg)

        # store additional fields
        out["host_mp_ids"] = mp_ids
        out["icsd_experimental"] = icsd_exp
        out["host_icsd_ids"] = icsd_ids
        out["cost"] = {
            "total": cost,
            "voltage": v_cost,
            "chg_stability": chg_stability_cost,
            "dchg_stability": dchg_stability_cost,
        }
        out["num_paths_found"] = num_paths_found
        out["mobility_inputs"] = mobility_inputs

        return out
