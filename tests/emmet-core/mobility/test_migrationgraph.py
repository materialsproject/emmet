import pytest
from monty.serialization import loadfn
from pymatgen.entries.computed_entries import ComputedEntry
from emmet.core.mobility.migrationgraph import MigrationGraphDoc


@pytest.fixture(scope="session")
def get_entries(test_dir):
    entry_Li = ComputedEntry("Li", -1.90753119)
    entries = loadfn(test_dir / "mobility/LiMnP2O7_batt.json")
    return (entries, entry_Li)

@pytest.fixture(scope="session")
def migration_graph(test_dir):
    """
    set the expected parameters for the migrationgraph
    """
    expected_properties = {
        "LiMnP2O7":{
            "max_distance": 5,
            "num_uhops": 8,
            "longest_hop": 4.92647,
            "shortest_hop": 2.77240
        }
    }

    return expected_properties


def test_from_entries_and_distance(migration_graph, get_entries):
    for expected in migration_graph.values():
        mgdoc = MigrationGraphDoc.from_entries_and_distance(
            battery_id="mp-1234",
            grouped_entries=get_entries[0],
            working_ion_entry=get_entries[1],
            hop_cutoff=5
        )

        mg = mgdoc.migration_graph
        res_d = {
            "max_distance": mgdoc.hop_cutoff,
            "num_uhops": len(mg.unique_hops),
            "longest_hop": sorted(mg.unique_hops.items(), key=lambda x: x[1]["hop_distance"])[-1][1]["hop_distance"],
            "shortest_hop": sorted(mg.unique_hops.items(), key=lambda x: x[1]["hop_distance"])[0][1]["hop_distance"]
        }
        for k, v in expected.items():
            print(res_d[k], pytest.approx(v, 0.01))
            assert res_d[k] == pytest.approx(v, 0.01)