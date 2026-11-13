import pytest
from monty.serialization import dumpfn, loadfn
from numpy.testing import assert_almost_equal
from emmet.core.io.pymatgen import MigrationGraph

from emmet.builders.utils import (
    _parse_kpoints,
    chemsys_permutations,
    get_hop_cutoff,
    get_potcar_stats,
    maximal_spanning_non_intersecting_subsets,
)
from emmet.core.settings import EmmetSettings
from emmet.core.testing_utils import DataArchive
from emmet.core.vasp.parse import DirectorySource, parse_calculation


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
    spinel_mg = loadfn(test_dir / "mobility/migration_graph_spinel_MgMn2O4.json.gz")
    nasicon_mg = loadfn(
        test_dir / "mobility/migration_graph_nasicon_MgV2(PO4)3.json.gz"
    )

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


@pytest.mark.parametrize("method", ("potcar", "pymatgen", "stored"))
def test_get_potcar_stats(method: str, tmp_path):
    calc_type = EmmetSettings().VASP_DEFAULT_INPUT_SETS

    try:
        potcar_stats = get_potcar_stats(method=method)
    except Exception as exc:
        if any(
            exc_str in str(exc) for exc_str in ("Set PMG_VASP_PSP_DIR", "No POTCAR for")
        ):
            # No Potcar library available, skip test
            return
        else:
            raise exc

    # ensure that all calc types are included in potcar_stats
    assert potcar_stats.keys() == calc_type.keys()

    for calc_type in potcar_stats:
        # ensure that each entry has needed fields for both
        # legacy and modern potcar validation
        assert all(
            [
                set(entry) == set(["hash", "keywords", "titel", "stats"])
                for entry in entries
            ]
            for entries in potcar_stats[calc_type].values()
        )

    if method == "stored":
        new_stats_path = tmp_path / "_temp_potcar_stats.json"
        dumpfn(potcar_stats, new_stats_path)

        new_potcar_stats = get_potcar_stats(
            method="stored", path_to_stored_stats=new_stats_path
        )
        assert all(
            potcar_stats[calc_type] == new_potcar_stats[calc_type]
            for calc_type in potcar_stats
        )


@pytest.mark.parametrize(
    "fixture, num_kpoints",
    [("magnetic_relax", 8 * 8 * 6), ("magnetic_static_volumetric", 22**3)],
)
def test_parse_kpoints_of_a_mesh(test_dir, fixture, num_kpoints):
    """The number of k-points of a mesh is the product of the divisions in `input.kpoints`.

    These calculations have no KPOINTS file: `input.kpoints` is the Gamma centered mesh
    that VASP made of KSPACING.
    """
    with DataArchive.extract(test_dir / "vasp" / f"{fixture}.json.gz") as directory:
        parsed = parse_calculation(
            DirectorySource.from_directory(directory)[0], "aaaaaaab"
        )
    assert parsed.errors == []
    assert _parse_kpoints(parsed.task) == num_kpoints
