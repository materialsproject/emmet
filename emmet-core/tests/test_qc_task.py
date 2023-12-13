import pytest
from tests.conftest_qchem import assert_schemas_equal, get_test_object


@pytest.mark.parametrize(
    "object_name, task_name",
    [
        pytest.param("SinglePointTest", "standard", id="SinglePointTest"),
        pytest.param("OptimizationTest", "standard", id="OptimizationTest"),
    ],
)  # Can add more later, something like freq, pesscan, ts,
# FFOptTest, once we get flows working for qchem in atomate2


def test_input_summary(test_dir, object_name, task_name):
    from monty.json import MontyDecoder, jsanitize
    from emmet.core.qc_tasks import InputDoc
    from emmet.core.qchem.calculation import Calculation

    test_object = get_test_object(object_name)
    dir_name = test_dir / "qchem" / test_object.folder

    files = test_object.task_files[task_name]
    calc_doc = Calculation.from_qchem_files(dir_name, task_name, **files)

    test_doc = InputDoc.from_qchem_calc_doc(calc_doc)
    valid_doc = test_object.task_doc["input"]
    assert_schemas_equal(test_doc, valid_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)


@pytest.mark.parametrize(
    "object_name, task_name",
    [
        pytest.param("SinglePointTest", "standard", id="SinglePointTest"),
        pytest.param("OptimizationTest", "standard", id="OptimizationTest"),
    ],
)
def test_output_summary(test_dir, object_name, task_name):
    from monty.json import MontyDecoder, jsanitize
    from emmet.core.qc_tasks import OutputDoc
    from emmet.core.qchem.calculation import Calculation

    test_object = get_test_object(object_name)
    dir_name = test_dir / "qchem" / test_object.folder

    files = test_object.task_files[task_name]
    calc_doc = Calculation.from_qchem_files(dir_name, task_name, **files)

    test_doc = OutputDoc.from_qchem_calc_doc(calc_doc)
    valid_doc = test_object.task_doc["output"]
    assert_schemas_equal(test_doc, valid_doc)

    # test document can be janitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)


@pytest.mark.parametrize(
    "object_name",
    [
        pytest.param("SinglePointTest", id="SinglePointTest"),
        pytest.param("OptimizationTest", id="OptimizationTest"),
    ],
)
def test_task_doc(test_dir, object_name):
    from monty.json import MontyDecoder, jsanitize
    from emmet.core.qc_tasks import TaskDoc

    test_object = get_test_object(object_name)
    dir_name = test_dir / "qchem" / test_object.folder
    test_doc = TaskDoc.from_directory(dir_name)
    assert_schemas_equal(test_doc, test_object.task_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)

    # Test that additional_fields works
    test_doc = TaskDoc.from_directory(dir_name, additional_fields={"foo": "bar"})
    assert test_doc.model_dump()["additional_fields"] == {"foo": "bar"}
