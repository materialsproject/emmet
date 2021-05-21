import pytest
from monty.serialization import loadfn
from pymatgen.apps.battery.conversion_battery import ConversionElectrode
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.core import Composition
from pymatgen.entries.computed_entries import ComputedEntry

from emmet.core.electrode import (
    ConversionElectrodeDoc,
    ConversionVoltagePairDoc,
    InsertionElectrodeDoc,
    InsertionVoltagePairDoc,
)
from emmet.core.migration import MigrationGraphDoc

__author__ = "Jimmy Shen"
__email__ = "jmmshn@gmail.com"


@pytest.fixture(scope="session")
def entries_lto(test_dir):
    """
    Recycle the test cases from pymatgen
    """
    entries = loadfn(test_dir / "LiTiO2_batt.json")
    for itr, ient in enumerate(entries):
        ient.entry_id = f"mp-{itr}"
    return entries


@pytest.fixture(scope="session")
def insertion_elec(test_dir) -> InsertionElectrode:
    """
    Insertion electrod object
    """
    entry_Li = ComputedEntry("Li", -1.90753119)
    entries_LTO = loadfn(test_dir / "LiTiO2_batt.json")
    return InsertionElectrode.from_entries(entries_LTO, entry_Li)


def test_StructureGroupDoc_from_ungrouped_entries(insertion_elec: InsertionElectrode):
    entries = insertion_elec.get_stable_entries()
    entry_li = ComputedEntry("Li", -1.90753119)
    dist_thresh = 4
    mg = MigrationGraphDoc.from_entries(
        entries=entries,
        working_ion_entry=entry_li,
        ltol=0.4,
        stol=0.6,
        angle_tol=15,
        symprec=0.1,
        min_distance_cutoff=dist_thresh,
    )

    assert len(mg.migration_graph_object.only_sites) == 6
    for u, v, d in mg.migration_graph_object.m_graph.graph.edges(data=True):
        assert d["hop_distance"] < dist_thresh
