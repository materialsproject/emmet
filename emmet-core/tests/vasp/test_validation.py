import pytest
import copy
from tests.conftest import assert_schemas_equal, get_test_object
from emmet.core.vasp.validation.validation import ValidationDoc
from emmet.core.tasks import TaskDoc

@pytest.mark.parametrize(
    "object_name",
    [
        # pytest.param("SiOptimizeDouble", id="SiOptimizeDouble"),
        pytest.param("SiStatic", id="SiStatic"),
        # pytest.param("SiNonSCFUniform", id="SiNonSCFUniform"),
    ],
)
def test_incar_common(test_dir, object_name):

    test_object = get_test_object(object_name)
    dir_name = test_dir / "vasp" / test_object.folder
    test_doc = TaskDoc.from_directory(dir_name)


    # ISMEAR wrong for nonmetal check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISMEAR"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ISMEAR" in reason for reason in temp_validation_doc.reasons])

    # SIGMA too high for nonmetal with ISMEAR = 0 check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISMEAR"] = 0
    temp_task_doc.input.parameters["SIGMA"] = 0.2
    temp_task_doc.output.bandgap = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["SIGMA" in reason for reason in temp_validation_doc.reasons])

    # SIGMA too high for nonmetal with ISMEAR = -5 check (should not error)
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISMEAR"] = -5
    temp_task_doc.input.parameters["SIGMA"] = 1000 # should not matter
    temp_task_doc.output.bandgap = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert not any(["SIGMA" in reason for reason in temp_validation_doc.reasons])

    # SIGMA too high for metal check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISMEAR"] = 1
    temp_task_doc.input.parameters["SIGMA"] = 0.5
    temp_task_doc.output.bandgap = 0
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["SIGMA" in reason for reason in temp_validation_doc.reasons])

    # ENCUT / ENMAX check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ENMAX"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ENCUT" in reason for reason in temp_validation_doc.reasons])

    # EDIFF check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["EDIFF"] = 1e-2
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["EDIFF:" in reason for reason in temp_validation_doc.reasons])

    # IALGO and ENINI checks
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["IALGO"] = 48
    temp_task_doc.input.parameters["ENINI"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ENINI" in reason for reason in temp_validation_doc.reasons])
    assert any(["IALGO" in reason for reason in temp_validation_doc.reasons])

    # NELECT check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["NELECT"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["NELECT" in reason for reason in temp_validation_doc.reasons])

    # NBANDS too low check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["NBANDS"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["NBANDS" in reason for reason in temp_validation_doc.reasons])

    # NBADNS too high check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["NBANDS"] = 1000
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["NBANDS" in reason for reason in temp_validation_doc.reasons])

    # LREAL check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.calcs_reversed[0].input.incar["LREAL"] = True # must change `incar` and not `parameters` for LREAL checks!
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LREAL" in reason for reason in temp_validation_doc.reasons])

    # LMAXPAW check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LMAXPAW"] = 0 # should be -100
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LMAXPAW" in reason for reason in temp_validation_doc.reasons])

    # NLSPLINE check for non-NMR calcs
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["NLSPLINE"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["NLSPLINE" in reason for reason in temp_validation_doc.reasons])

    # FFT grid check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.calcs_reversed[0].input.incar["NGX"] = 1 # must change `incar` *and* `parameters` for NG_ checks!
    temp_task_doc.input.parameters["NGX"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["NGX" in reason for reason in temp_validation_doc.reasons])

    # ADDGRID check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ADDGRID"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ADDGRID" in reason for reason in temp_validation_doc.reasons])

    # to be continued, starting with hybrid functional params



    # raise ValueError(temp_validation_doc.reasons)










### TODO: add tests for many other MP input sets (e.g. MPNSCFSet, MPNMRSet, MPScanRelaxSet, Hybrid sets, etc.)
    ### TODO: add ENAUG check for SCAN workflows
    ### TODO: add check for wrong ismear (e.g. -5) for metal relaxation


