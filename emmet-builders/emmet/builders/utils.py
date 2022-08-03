from typing import Set, Union
import sys
import os
from itertools import chain, combinations
from pymatgen.core import Structure
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph


def maximal_spanning_non_intersecting_subsets(sets) -> Set[Set]:
    """
    Finds the maximal spanning non intersecting subsets of a group of sets
    This is usefull for parsing out the sandboxes and figuring out how to group
    and calculate these for thermo documents

    sets (set(frozenset)): sets of keys to subsect, expected as a set of frozensets
    """
    to_return_subsets = []

    # Find the overlapping portions and independent portions
    for subset in sets:
        for other_set in sets:
            subset = frozenset(subset.intersection(other_set)) or subset
        if subset:
            to_return_subsets.append(subset)

    # Remove accounted for elements and recurse on remaining sets
    accounted_elements = set(chain.from_iterable(to_return_subsets))
    sets = {frozenset(subset - accounted_elements) for subset in sets}
    sets = {subset for subset in sets if subset}

    if sets:
        to_return_subsets.extend(maximal_spanning_non_intersecting_subsets(sets))

    return set(to_return_subsets)


def chemsys_permutations(chemsys) -> Set:
    # Function to get all relevant chemical subsystems
    # e.g. for Li-Mn-O returns Li, Li-Mn, Li-Mn-O, Li-O, Mn, Mn-O, O
    elements = chemsys.split("-")
    return {
        "-".join(sorted(c))
        for c in chain(
            *[combinations(elements, i) for i in range(1, len(elements) + 1)]
        )
    }


def get_hop_cutoff(
    migration_graph_struct: Structure,
    mobile_specie: str,
    algorithm: str = "min_distance",
    min_hop_distance: float = 1,
    max_hop_distance: float = 7,
) -> Union[float, None]:
    """
    A function to get an appropriate hop distance cutoff for a given migration
    graph structure which can be used for MigrationGraph.with_distance()

    migration_graph_struct (Structure): the host structure with all working ion
        sites for consideration filled.
        Can get via MigrationGraph.get_structure_from_entries()
    mobile_specie (str): specifies the mobile specie in migration_graph_struct
        (e.g. "Li", "Mg").
    algorithm (str): specify the algorithm to use for getting the hop cutoff.
        "min_distance" =  incrementally increases the hop cutoff to get the
            minimum cutoff value that results in finding a path
        "hops_based" = incrementally increases the hop cutoff until either
            1) the largest hop length exceeds 2x the smallest hop length or
            2) the next incremental increase of the cutoff results in the total
            number of unique hops to exceeding more than 1.5x the previous
            number of unique hops
    """
    d = min_hop_distance
    mg = MigrationGraph.with_distance(
        structure=migration_graph_struct,
        migrating_specie=mobile_specie,
        max_distance=d,
    )
    mg.assign_cost_to_graph(["hop_distance"])
    paths = list(mg.get_path())

    if algorithm == "min_distance":
        while len(paths) == 0 and d < max_hop_distance:
            d = d * 1.1
            mg = MigrationGraph.with_distance(
                structure=migration_graph_struct,
                migrating_specie=mobile_specie,
                max_distance=d,
            )
            mg.assign_cost_to_graph(["hop_distance"])
            paths = list(mg.get_path())
        if d > max_hop_distance:
            return 0
        else:
            return d
    elif algorithm == "hops_based":
        # Thank you to Alex Nguyen Ngoc (alexnguyen0512) for their initial
        # work in developing this algorithm

        # incrementally increase d until at least one path is found
        # this sets d at the minimum distance that results in a path
        while len(paths) == 0 and d < max_hop_distance:
            d = d * 1.1
            mg = MigrationGraph.with_distance(
                structure=migration_graph_struct,
                migrating_specie=mobile_specie,
                max_distance=d,
            )
            mg.assign_cost_to_graph(["hop_distance"])
            paths = list(mg.get_path())
        if d > max_hop_distance:
            return 0

        # once a path is found, get the smallest hop distance and
        # the number of unique hops
        smallest_hop_distance = min(
            [v["hop_distance"] for v in mg.unique_hops.values()]
        )
        num_unique_hops = len(mg.unique_hops)

        # continually incrementally increase d until either...
        # 1) the largest hop distance exceeds 2x the smallest hop distance
        # 2) the number of unique hops spikes (increases by more than 1.5x)
        while (
            max([v["hop_distance"] for v in mg.unique_hops.values()])
            <= smallest_hop_distance * 2
            and d < max_hop_distance
        ):
            d = d * 1.1
            mg = MigrationGraph.with_distance(
                structure=migration_graph_struct,
                migrating_specie=mobile_specie,
                max_distance=d,
            )

            # check for spike in number of hops
            if len(mg.unique_hops) >= 1.5 * num_unique_hops and num_unique_hops >= 4:
                return d / 1.1  # return value of d before the number of hops spiked

            num_unique_hops = len(mg.unique_hops)

        return d

    else:
        return None


# From: https://stackoverflow.com/a/45669280
class HiddenPrints:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout
