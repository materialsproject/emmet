from itertools import combinations, chain
from emmet.builders.utils import (
    maximal_spanning_non_intersecting_subsets,
    chemsys_permutations,
)


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
