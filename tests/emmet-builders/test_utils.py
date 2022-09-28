from emmet.builders.utils import (
    chemsys_permutations,
    maximal_spanning_non_intersecting_subsets,
    get_hop_cutoff,
)
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
from numpy.testing import assert_almost_equal
from monty.serialization import loadfn


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


def test_get_hop_cutoff(test_dir):
    spinel_mg = loadfn(test_dir / "mobility/migration_graph_spinel_MgMn2O4.json")
    nasicon_mg = loadfn(test_dir / "mobility/migration_graph_nasicon_MgV2(PO4)3.json")

    # tests for "min_distance" algorithm
    assert_almost_equal(
        get_hop_cutoff(spinel_mg.structure, "Mg", algorithm="min_distance"),
        1.95,
        decimal=2,
    )
    assert_almost_equal(
        get_hop_cutoff(nasicon_mg.structure, "Mg", algorithm="min_distance"),
        3.80,
        decimal=2,
    )

    # test for "hops_based" algorithm, terminated by number of unique hops condition
    d = get_hop_cutoff(spinel_mg.structure, "Mg", algorithm="hops_based")
    check_mg = MigrationGraph.with_distance(spinel_mg.structure, "Mg", d)
    assert_almost_equal(d, 4.18, decimal=2)
    assert len(check_mg.unique_hops) == 5

    # test for "hops_based" algorithm, terminated by the largest hop length condition
    d = get_hop_cutoff(nasicon_mg.structure, "Mg", algorithm="hops_based")
    check_mg = MigrationGraph.with_distance(nasicon_mg.structure, "Mg", d)
    assert_almost_equal(d, 4.59, decimal=2)
    assert len(check_mg.unique_hops) == 6
