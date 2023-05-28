import pytest
from monty.serialization import loadfn
from pymatgen.core import Composition

from emmet.core.structure_group import StructureGroupDoc


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
def entries_lfeo(test_dir):
    """
    Recycle the test cases from pymatgen
    """
    entries = loadfn(test_dir / "Li-Fe-O.json")
    return entries


def test_StructureGroupDoc_from_grouped_entries(entries_lto):
    sgroup_doc = StructureGroupDoc.from_grouped_entries(
        entries_lto,
        ignored_specie="Li",
    )
    assert sgroup_doc.group_id == "mp-0_Li"
    assert sgroup_doc.material_ids == ["mp-0", "mp-1", "mp-2", "mp-3", "mp-4", "mp-5"]
    assert sgroup_doc.framework_formula == "TiO2"
    assert sgroup_doc.ignored_specie == "Li"
    assert sgroup_doc.chemsys == "Li-O-Ti"
    assert sgroup_doc.has_distinct_compositions is True


@pytest.mark.skip(reason="Temp skip for spglib seg fault")
def test_StructureGroupDoc_from_ungrouped_entries(entries_lfeo):
    entry_dict = {ient.entry_id: ient for ient in entries_lfeo}
    sgroup_docs = StructureGroupDoc.from_ungrouped_structure_entries(
        entries_lfeo, ignored_specie="Li"
    )

    # Make sure that all the structure in each group has the same framework
    for sgroup_doc in sgroup_docs:
        framework_ref = sgroup_doc.framework_formula
        ignored = sgroup_doc.ignored_specie
        for entry_id in sgroup_doc.material_ids:
            dd_ = entry_dict[entry_id].composition.as_dict()
            if ignored in dd_:
                dd_.pop(ignored)
            framework = Composition.from_dict(dd_).reduced_formula
            assert framework == framework_ref
