import pytest
from tests.conftest import assert_schemas_equal, get_test_object


@pytest.mark.parametrize(
    "object_name",
    [
        pytest.param("SiOptimizeDouble", id="SiOptimizeDouble"),
        pytest.param("SiStatic", id="SiStatic"),
        pytest.param("SiNonSCFUniform", id="SiNonSCFUniform"),
    ],
)
def test_analysis_summary(test_dir, object_name):
    from monty.json import MontyDecoder, jsanitize

    from emmet.core.tasks import AnalysisDoc
    from emmet.core.vasp.calculation import Calculation

    test_object = get_test_object(object_name)
    dir_name = test_dir / "vasp" / test_object.folder

    calcs_reversed = []
    for task_name, files in test_object.task_files.items():
        doc, _ = Calculation.from_vasp_files(dir_name, task_name, **files)
        calcs_reversed.append(doc)
        # The 2 tasks of double-relaxation have been reversed in
        # "/atomate2/tests/vasp/schemas/conftest.py" for "SiOptimizeDouble"
        # task_files are in the order of {"relax2","relax1"}

    test_doc = AnalysisDoc.from_vasp_calc_docs(calcs_reversed)
    valid_doc = test_object.task_doc["analysis"]
    assert_schemas_equal(test_doc, valid_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)


@pytest.mark.parametrize(
    "object_name,task_name",
    [
        pytest.param("SiOptimizeDouble", "relax1", id="SiOptimizeDouble"),
        pytest.param("SiStatic", "standard", id="SiStatic"),
        pytest.param("SiNonSCFUniform", "standard", id="SiNonSCFUniform"),
    ],
)
def test_input_summary(test_dir, object_name, task_name):
    from monty.json import MontyDecoder, jsanitize

    from emmet.core.tasks import InputDoc
    from emmet.core.vasp.calculation import Calculation

    test_object = get_test_object(object_name)
    dir_name = test_dir / "vasp" / test_object.folder

    files = test_object.task_files[task_name]
    calc_doc, _ = Calculation.from_vasp_files(dir_name, task_name, **files)

    test_doc = InputDoc.from_vasp_calc_doc(calc_doc)
    valid_doc = test_object.task_doc["input"]
    assert_schemas_equal(test_doc, valid_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)


@pytest.mark.parametrize(
    "object_name,task_name",
    [
        pytest.param("SiOptimizeDouble", "relax2", id="SiOptimizeDouble"),
        pytest.param("SiStatic", "standard", id="SiStatic"),
        pytest.param("SiNonSCFUniform", "standard", id="SiNonSCFUniform"),
    ],
)
def test_output_summary(test_dir, object_name, task_name):
    from monty.json import MontyDecoder, jsanitize

    from emmet.core.tasks import OutputDoc
    from emmet.core.vasp.calculation import Calculation

    test_object = get_test_object(object_name)
    dir_name = test_dir / "vasp" / test_object.folder

    files = test_object.task_files[task_name]
    calc_doc, _ = Calculation.from_vasp_files(dir_name, task_name, **files)

    test_doc = OutputDoc.from_vasp_calc_doc(calc_doc)
    valid_doc = test_object.task_doc["output"]
    assert_schemas_equal(test_doc, valid_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)


@pytest.mark.parametrize(
    "object_name",
    [
        pytest.param("SiOptimizeDouble", id="SiOptimizeDouble"),
        pytest.param("SiStatic", id="SiStatic"),
        pytest.param("SiNonSCFUniform", id="SiNonSCFUniform"),
    ],
)
def test_task_doc(test_dir, object_name):
    from monty.json import MontyDecoder, jsanitize

    from emmet.core.tasks import TaskDoc

    test_object = get_test_object(object_name)
    dir_name = test_dir / "vasp" / test_object.folder
    test_doc = TaskDoc.from_directory(dir_name)
    assert_schemas_equal(test_doc, test_object.task_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)

    # Test that additional_fields works
    test_doc = TaskDoc.from_directory(dir_name, additional_fields={"foo": "bar"})
    assert test_doc.model_dump()["foo"] == "bar"
