from itertools import combinations, chain
from emmet.builders.utils import maximal_spanning_non_intersecting_subsets


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
