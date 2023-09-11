import pytest
import copy
from tests.conftest import assert_schemas_equal, get_test_object
from emmet.core.vasp.validation.validation import ValidationDoc
from emmet.core.tasks import TaskDoc

# Unsure what this is for, need input on if this is necessary ###################
@pytest.mark.parametrize(
    "object_name",
    [
        pytest.param("SiOptimizeDouble", id="SiOptimizeDouble"),
        pytest.param("SiStatic", id="SiStatic"),
        pytest.param("SiNonSCFUniform", id="SiNonSCFUniform"),
    ],
)
def test_incar(test_dir, object_name):

    test_object = get_test_object(object_name)
    dir_name = test_dir / "vasp" / test_object.folder
    test_doc = TaskDoc.from_directory(dir_name)

    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["NBANDS"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    print(temp_validation_doc.reasons)
    assert "NBANDS" in temp_validation_doc.reasons[0]

    raise ValueError(test_doc.structure)



