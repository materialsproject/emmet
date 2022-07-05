from emmet.builders.utils import (
    chemsys_permutations,
    maximal_spanning_non_intersecting_subsets,
    get_working_ion_entries,
)
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry


def test_maximal_spanning_non_intersecting_subsets():

    assert maximal_spanning_non_intersecting_subsets([{"A"}, {"A", "B"}]) == {
        frozenset(d) for d in [{"A"}, {"B"}]
    }

    assert maximal_spanning_non_intersecting_subsets([{"A", "B"}, {"A", "B", "C"}]) == {
        frozenset(d) for d in [{"A", "B"}, {"C"}]
    }

    assert maximal_spanning_non_intersecting_subsets(
        [{"A", "B"}, {"A", "B", "C"}, {"D"}]
    ) == {frozenset(d) for d in [{"A", "B"}, {"C"}, {"D"}]}


def test_chemsys_permutations(test_dir):
    assert len(chemsys_permutations("Sr")) == 1
    assert len(chemsys_permutations("Sr-Hf")) == 3
    assert len(chemsys_permutations("Sr-Hf-O")) == 7


def test_get_working_ion_entries():
    all_wi = get_working_ion_entries(working_ions="all")
    all_with_struct = get_working_ion_entries(working_ions="all", inc_structure="final")
    sub_wi = get_working_ion_entries(working_ions=["Li", "Na", "Mg"])
    single_wi = get_working_ion_entries(working_ions="Li")

    assert type(all_wi) == dict
    assert type(all_wi["Li"]) == ComputedEntry
    assert type(all_with_struct) == dict
    assert type(all_with_struct["Li"]) == ComputedStructureEntry
    assert type(sub_wi) == dict
    assert len(sub_wi.keys()) == 3
    assert type(sub_wi["Li"]) == ComputedEntry
    assert type(single_wi) == ComputedEntry
