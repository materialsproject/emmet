import numpy as np
import pytest
from monty.serialization import loadfn
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.entries.computed_entries import ComputedEntry
from emmet.core.mobility.migrationgraph import MigrationGraphDoc


@pytest.fixture(scope="session")
def get_entries(test_dir):
    entry_Li = ComputedEntry("Li", -1.90753119)
    entries = loadfn(test_dir / "mobility/LiMnP2O7_batt.json")
    return (entries, entry_Li)


@pytest.fixture(scope="session")
def migration_graph_prop():
    """
    set the expected parameters for the migrationgraph
    """
    expected_properties = {
        "LiMnP2O7": {
            "max_distance": 5,
            "num_uhops": 8,
            "longest_hop": 4.92647,
            "shortest_hop": 2.77240
        }
    }
    return expected_properties


@pytest.fixture(scope="session")
def mg_for_sc_fields(test_dir):
    """
    get MigrationGraph object generated with methods from pymatgen.analysis.diffusion for testing generate_sc_fields
    """
    mg_for_sc = loadfn(test_dir / "mobility/mg_for_sc.json")
    return mg_for_sc


def test_from_entries_and_distance(migration_graph_prop, get_entries):
    for expected in migration_graph_prop.values():
        sm = StructureMatcher()
        mgdoc = MigrationGraphDoc.from_entries_and_distance(
            battery_id="mp-1234",
            grouped_entries=get_entries[0],
            working_ion_entry=get_entries[1],
            hop_cutoff=5,
            sm=sm,
            min_length=7,
            minmax_num_atoms=(80, 160)
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


def test_generate_sc_fields(mg_for_sc_fields):
    sm = StructureMatcher()
    host_sc, sc_mat, min_length, min_max_num_atoms, coords_dict, combo = MigrationGraphDoc.generate_sc_fields(mg_for_sc_fields, 7, (80, 160), sm)
    sc_mat_inv = np.linalg.inv(sc_mat)
    expected_sc_list = []

    for one_hop in mg_for_sc_fields.unique_hops.values():
        host_sc_insert = host_sc.copy()
        host_sc_insert.insert(0, "Li", np.dot(one_hop["ipos"], sc_mat_inv))
        host_sc_insert.insert(0, "Li", np.dot(one_hop["epos"], sc_mat_inv))
        expected_sc_list.append(host_sc_insert)

    for one_combo in combo:
        hop_sc = host_sc.copy()
        sc_iindex, sc_eindex = list(map(int, one_combo.split("+")))
        sc_isite = coords_dict[sc_iindex]["site"]
        sc_esite = coords_dict[sc_eindex]["site"]
        hop_sc.insert(0, "Li", sc_isite.frac_coords)
        hop_sc.insert(0, "Li", sc_esite.frac_coords)
        check_sc_list = [sm.fit(hop_sc, check_sc) for check_sc in expected_sc_list]
        assert sum(check_sc_list) >= 1
