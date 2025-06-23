import numpy as np
import pytest
from monty.serialization import loadfn
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.entries.computed_entries import ComputedEntry
from emmet.core.mobility.migrationgraph import MigrationGraphDoc


@pytest.fixture(scope="session")
def get_entries(test_dir):
    entry_Li = ComputedEntry("Li", -1.90753119)
    entries = loadfn(test_dir / "mobility/LiMnP2O7_batt.json.gz")
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
            "shortest_hop": 2.77240,
            "min_length_sc": 7,
            "minmax_num_atoms": (80, 160),
        }
    }
    return expected_properties


@pytest.fixture(scope="session")
def mg_for_sc_fields(test_dir):
    """
    get MigrationGraph object generated with methods from pymatgen.analysis.diffusion for testing generate_sc_fields
    """
    mg_for_sc = loadfn(test_dir / "mobility/mg_for_sc.json.gz")
    return mg_for_sc


@pytest.fixture(scope="session")
def match_mgdoc_npr(test_dir):
    """
    get the MigrationGraphDoc and NebPathwayResult objects to test matching functions
    """
    match_mgdoc = loadfn(test_dir / "mobility/test_match_mgdoc.json.gz")
    match_npr = loadfn(test_dir / "mobility/test_match_npr_doc.json.gz")
    return (match_mgdoc, match_npr)


@pytest.fixture(scope="session")
def match_mgd_prop():
    """
    set the epected parameters for migrationgraph docs after matching with NebPathwayResult
    """
    return {"num_paths": 2, "len_of_paths": [2, 2], "max_costs": [0.82334, 0.82334]}


@pytest.fixture(scope="session")
def match_mgd_w_cost_prop():
    """
    set the epected parameters for migrationgraph docs after matching with NebPathwayResult
    """
    return {"costs": [0.82334, 0.03334], "hop_keys": ["0+1", "2+1"]}


@pytest.mark.skip(
    reason="Incompatible with Pymatgen>=2024.9.10, regression testing in progress..."
)
def test_from_entries_and_distance(migration_graph_prop, get_entries):
    for expected in migration_graph_prop.values():
        mgdoc = MigrationGraphDoc.from_entries_and_distance(
            battery_id="mp-1234",
            grouped_entries=get_entries[0],
            working_ion_entry=get_entries[1],
            hop_cutoff=5,
            populate_sc_fields=True,
            min_length_sc=7,
            minmax_num_atoms=(80, 160),
        )

        mg = mgdoc.migration_graph
        res_d = {
            "max_distance": mgdoc.hop_cutoff,
            "num_uhops": len(mg.unique_hops),
            "longest_hop": sorted(
                mg.unique_hops.items(), key=lambda x: x[1]["hop_distance"]
            )[-1][1]["hop_distance"],
            "shortest_hop": sorted(
                mg.unique_hops.items(), key=lambda x: x[1]["hop_distance"]
            )[0][1]["hop_distance"],
            "min_length_sc": mgdoc.min_length_sc,
            "minmax_num_atoms": mgdoc.minmax_num_atoms,
        }
        for k, v in expected.items():
            assert res_d[k] == pytest.approx(v, 0.01)


def test_generate_sc_fields(mg_for_sc_fields):
    sm = StructureMatcher()
    (
        host_sc,
        sc_mat,
        min_length,
        min_max_num_atoms,
        coords_dict,
        combo,
    ) = MigrationGraphDoc.generate_sc_fields(
        mg_for_sc_fields, 7, (80, 160), sm, "complete"
    )
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
        sc_isite = coords_dict[sc_iindex]["site_frac_coords"]
        sc_esite = coords_dict[sc_eindex]["site_frac_coords"]
        hop_sc.insert(0, "Li", sc_isite)
        hop_sc.insert(0, "Li", sc_esite)
        check_sc_list = [sm.fit(hop_sc, check_sc) for check_sc in expected_sc_list]
        assert sum(check_sc_list) >= 1


@pytest.mark.skip(
    reason="Incompatible with Pymatgen>=2024.9.10, regression testing in progress..."
)
def test_get_distinct_hop_sites(get_entries):
    mgdoc = MigrationGraphDoc.from_entries_and_distance(
        battery_id="mp-1234",
        grouped_entries=get_entries[0],
        working_ion_entry=get_entries[1],
        hop_cutoff=5,
        populate_sc_fields=True,
        min_length_sc=7,
        minmax_num_atoms=(80, 160),
    )
    (
        dis_sites_list,
        dis_combo_list,
        combo_mapping,
    ) = MigrationGraphDoc.get_distinct_hop_sites(
        mgdoc.inserted_ion_coords, mgdoc.insert_coords_combo
    )
    for one_test_combo in ["0+1", "0+2", "0+3", "0+4", "0+5", "0+6", "1+7", "1+2"]:
        assert one_test_combo in dis_combo_list
    assert combo_mapping == {
        "0+1": "9+4",
        "0+2": "9+8",
        "0+3": "9+6",
        "0+4": "9+16",
        "0+5": "9+17",
        "0+6": "9+13",
        "1+7": "4+0",
        "1+2": "4+8",
    }


def test_get_paths_summary_with_neb_res(match_mgdoc_npr, match_mgd_prop):
    mgdoc, npr = match_mgdoc_npr
    paths_summary, mg_new = MigrationGraphDoc.get_paths_summary_with_neb_res(
        mgdoc.migration_graph, npr, "energy_range"
    )
    res_prop = {
        "num_paths": len(paths_summary),
        "len_of_paths": [len(v) for v in paths_summary.values()],
        "max_costs": [max([i.cost for i in path]) for path in paths_summary.values()],
    }

    for k, v in match_mgd_prop.items():
        assert res_prop[k] == pytest.approx(v, 0.01)


def test_augment_from_mgd_and_npr(match_mgdoc_npr, match_mgd_w_cost_prop):
    mgdoc, npr = match_mgdoc_npr
    mgd_w_cost = MigrationGraphDoc.augment_from_mgd_and_npr(
        mgd=mgdoc, npr=npr, barrier_type="energy_range"
    )
    assert mgd_w_cost.migration_graph_w_cost is not None
    res_uhops = mgd_w_cost.migration_graph_w_cost.unique_hops
    res_uhops = [v for k, v in sorted(res_uhops.items())]
    res_prop = {
        "costs": [uhop["cost"] for uhop in res_uhops],
        "hop_keys": [uhop["hop_key"] for uhop in res_uhops],
    }
    for k, v in match_mgd_w_cost_prop.items():
        assert res_prop[k] == pytest.approx(v, 0.01)
