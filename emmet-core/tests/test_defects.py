from emmet.core.defect import DefectTaskDoc


def test_parsing_defect_directory(test_dir):
    from pymatgen.analysis.defects.core import Defect

    defect_run = test_dir / "vasp/defect_run"
    defect_task = DefectTaskDoc.from_directory(defect_run)
    assert isinstance(defect_task.defect, Defect)
    assert defect_task.defect_name == "O_Te"
