from emmet.core.defect import DefectTaskDoc
from emmet.core.testing_utils import DataArchive


def test_parsing_defect_directory(test_dir):
    from pymatgen.analysis.defects.core import Defect

    with DataArchive.extract(test_dir / "vasp/defect_run.json.gz") as temp_dir:
        defect_task = DefectTaskDoc.from_directory(temp_dir)
    assert isinstance(defect_task.defect, Defect)
    assert defect_task.defect_name == "O_Te"
