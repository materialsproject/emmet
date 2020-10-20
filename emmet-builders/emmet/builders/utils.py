from itertools import chain, combinations
from typing import Set


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
    # Fancy way of getting every unique permutation of elements for all
    # possible number of elements:
    elements = chemsys.split("-")
    return {
        "-".join(sorted(c))
        for c in chain(
            *[combinations(elements, i) for i in range(1, len(elements) + 1)]
        )
    }
