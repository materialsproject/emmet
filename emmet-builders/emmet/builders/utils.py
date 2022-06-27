from typing import Set, List, Union, Dict
from itertools import chain, combinations
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from pymatgen.ext.matproj import MPRester
from emmet.builders.materials.electrodes import WORKING_IONS


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


def get_working_ion_entries(
    working_ions: Union[str, List[str]] = "all",
    inc_structure: Union[str, None] = None,
) -> Union[ComputedEntry, ComputedStructureEntry, Dict]:
    """
    working_ions (str, List): If single working ion string is provided
        (e.g. "Li" or "Na"), a single ComputedEntry or ComputedStructureEntry
        will be returned. If a list of working ion strings are provided,
        (e.g. ["Li","Na"]), a dictionary will be returned where working ion
        strings are the keys and the values are corresponding ComputedEntries
        or ComputedStructureEntries. By default a dictionary will be returned
        based on WORKING_IONS from emmet.builders.materials.electrodes
    inc_structure (str): If None, entries returned are ComputedEntries.
        If inc_structure="initial", ComputedStructureEntries with initial
        structures are returned. Otherwise, ComputedStructureEntries with
        final structures are returned.
    """
    mpr = MPRester()

    if working_ions == "all":
        output = {}
        for wi in WORKING_IONS:
            all_entries = mpr.get_entries_in_chemsys([wi], inc_structure=inc_structure)
            output.update({wi: min(all_entries, key=lambda k: k.energy_per_atom)})
        return output

    elif type(working_ions) == list:
        output = {}
        for wi in working_ions:
            all_entries = mpr.get_entries_in_chemsys([wi], inc_structure=inc_structure)
            output.update({wi: min(all_entries, key=lambda k: k.energy_per_atom)})
        return output

    elif type(working_ions) == str:
        all_entries = mpr.get_entries_in_chemsys(
            [working_ions], inc_structure=inc_structure
        )
        return min(all_entries, key=lambda k: k.energy_per_atom)
