import json
import os
from pprint import pprint

import pytest
from monty.json import MontyDecoder
from pymatgen import Composition
from pymatgen.apps.battery.conversion_battery import ConversionElectrode
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.apps.battery.tests.test_insertion_battery import test_dir as PMG_TESTDIR
from pymatgen.entries.computed_entries import ComputedEntry

from emmet.core.electrode import (
    ConversionElectrodeDoc,
    ConversionVoltagePairDoc,
    InsertionElectrodeDoc,
    InsertionVoltagePairDoc,
)


@pytest.fixture
def insertion_elec():
    """
    Recycle the test cases from pymatgen
    """
    entry_Li = ComputedEntry("Li", -1.90753119)
    entry_Ca = ComputedEntry("Ca", -1.99689568)

    with open(os.path.join(PMG_TESTDIR, "LiTiO2_batt.json"), "r") as f:
        entries_LTO = json.load(f, cls=MontyDecoder)

    with open(os.path.join(PMG_TESTDIR, "MgVO_batt.json"), "r") as file:
        entries_MVO = json.load(file, cls=MontyDecoder)

    with open(os.path.join(PMG_TESTDIR, "Mg_batt.json"), "r") as file:
        entry_Mg = json.load(file, cls=MontyDecoder)

    with open(os.path.join(PMG_TESTDIR, "CaMoO2_batt.json"), "r") as f:
        entries_CMO = json.load(f, cls=MontyDecoder)

    ie_LTO = InsertionElectrode.from_entries(entries_LTO, entry_Li)
    ie_MVO = InsertionElectrode.from_entries(entries_MVO, entry_Mg)
    ie_CMO = InsertionElectrode.from_entries(entries_CMO, entry_Ca)

    return {
        "LTO": (ie_LTO, entries_LTO[0].structure, entry_Li),
        "MVO": (ie_MVO, entries_MVO[0].structure, entry_Mg),
        "CMO": (ie_CMO, entries_CMO[0].structure, entry_Ca),
    }


kmap = {"specific_energy": "energy_grav", "energy_density": "energy_vol"}


@pytest.fixture
def conversion_elec():
    formulas = ["LiCoO2", "FeF3", "MnO2"]
    conversion_eletrodes = {}
    for f in formulas:

        with open(os.path.join(PMG_TESTDIR, f + "_batt.json"), "r") as fid:
            entries = json.load(fid, cls=MontyDecoder)
        if f in ["LiCoO2", "FeF3"]:
            working_ion = "Li"
        elif f in ["MnO2"]:
            working_ion = "Mg"
        c = ConversionElectrode.from_composition_and_entries(
            Composition(f), entries, working_ion_symbol=working_ion
        )
        conversion_eletrodes[f] = {
            "working_ion": working_ion,
            "CE": c,
            "entries": entries,
        }

    expected_properties = {
        "LiCoO2": {
            "average_voltage": 2.26940307125,
            "capacity_grav": 903.19752911225669,
            "capacity_vol": 2903.35804724,
            "energy_grav": 2049.7192465127678,
            "energy_vol": 6588.8896693479574,
        },
        "FeF3": {
            "average_voltage": 3.06179925889,
            "capacity_grav": 601.54508701578118,
            "capacity_vol": 2132.2069115142394,
            "energy_grav": 1841.8103016131706,
            "energy_vol": 6528.38954147,
        },
        "MnO2": {
            "average_voltage": 1.7127027687901726,
            "capacity_grav": 790.9142070034802,
            "capacity_vol": 3543.202003526853,
            "energy_grav": 1354.6009522103434,
            "energy_vol": 6068.451881823329,
        },
    }

    return {k: (conversion_eletrodes[k], expected_properties[k]) for k in formulas}


def test_InsertionDocs(insertion_elec):
    for k, (elec, struct, wion_entry) in insertion_elec.items():
        # Make sure that main document can be created using an InsertionElectrode object
        ie = InsertionElectrodeDoc.from_entries(
            grouped_entries=elec._stable_entries,
            working_ion_entry=wion_entry,
            task_id="mp-1234",
            host_structure=struct,
        )
        assert ie.average_voltage == elec.get_average_voltage()
        # Make sure that each adjacent pair can be converted into a sub electrode
        for sub_elec in elec.get_sub_electrodes(adjacent_only=True):
            vp = InsertionVoltagePairDoc.from_sub_electrode(sub_electrode=sub_elec)
            assert vp.average_voltage == sub_elec.get_average_voltage()


def test_ConversionDocs(conversion_elec):
    for k, (elec, expected) in conversion_elec.items():
        # Make sure that main document can be created using an InsertionElectrode object
        for sub_elec in elec["CE"].get_sub_electrodes(adjacent_only=True):
            vp = ConversionVoltagePairDoc.from_sub_electrode(sub_electrode=sub_elec)
            assert vp.average_voltage == sub_elec.get_average_voltage()

        vp = ConversionElectrodeDoc.from_composition_and_entries(
            Composition(k),
            entries=elec["entries"],
            working_ion_symbol=elec["working_ion"],
            task_id="mp-1234",
        )
        res_d = vp.dict()
        for k, v in expected.items():
            assert res_d[k] == pytest.approx(v, 0.01)
