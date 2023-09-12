import pytest
import copy
from tests.conftest import assert_schemas_equal, get_test_object
from emmet.core.vasp.validation.validation import ValidationDoc
from emmet.core.tasks import TaskDoc

@pytest.mark.parametrize(
    "object_name",
    [
        pytest.param("SiOptimizeDouble", id="SiOptimizeDouble"),
        # pytest.param("SiStatic", id="SiStatic"),
        # pytest.param("SiNonSCFUniform", id="SiNonSCFUniform"),
    ],
)
def test_incar_common(test_dir, object_name):

    test_object = get_test_object(object_name)
    dir_name = test_dir / "vasp" / test_object.folder
    test_doc = TaskDoc.from_directory(dir_name)

    # sanitize with monty or something here????? #######################################


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
    temp_task_doc.input.parameters["NGX"] = 1 # must change `incar` *and* `parameters` for NG_ checks!
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["NGX" in reason for reason in temp_validation_doc.reasons])

    # ADDGRID check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ADDGRID"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ADDGRID" in reason for reason in temp_validation_doc.reasons])

    # LHFCALC check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LHFCALC"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LHFCALC" in reason for reason in temp_validation_doc.reasons])

    # AEXX check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["AEXX"] = 1 # should never be set to this
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["AEXX" in reason for reason in temp_validation_doc.reasons])

    # AGGAC check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["AGGAC"] = 0.5 # should never be set to this
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["AGGAC" in reason for reason in temp_validation_doc.reasons])

    # AGGAX check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["AGGAX"] = 0.5 # should never be set to this
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["AGGAX" in reason for reason in temp_validation_doc.reasons])

    # ALDAX check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ALDAX"] = 0.5 # should never be set to this
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ALDAX" in reason for reason in temp_validation_doc.reasons])

    # AMGGAX check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["AMGGAX"] = 0.5 # should never be set to this
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["AMGGAX" in reason for reason in temp_validation_doc.reasons])

    # ALDAC check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ALDAC"] = 0.5 # should never be set to this
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ALDAC" in reason for reason in temp_validation_doc.reasons])

    # AMGGAC check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["AMGGAC"] = 0.5 # should never be set to this
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["AMGGAC" in reason for reason in temp_validation_doc.reasons])

    # IBRION check
    ### TODO: add check for an MP input set that uses an IBRION other than [-1, 1, 2]
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["IBRION"] = 3
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["IBRION" in reason for reason in temp_validation_doc.reasons])

    # ISIF check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISIF"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ISIF" in reason for reason in temp_validation_doc.reasons])

    # PSTRESS check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["PSTRESS"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["PSTRESS" in reason for reason in temp_validation_doc.reasons])

    # POTIM check
    ### TODO: add in second check for POTIM that checks for large energy changes between ionic steps
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["POTIM"] = 10
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["POTIM" in reason for reason in temp_validation_doc.reasons])

    # SCALEE check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["SCALEE"] = 0.9
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["SCALEE" in reason for reason in temp_validation_doc.reasons])

    # EDIFFG / force convergence check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["EDIFFG"] = 0.01
    temp_task_doc.output.forces = [[10,10,10],[10,10,10]]
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["CONVERGENCE" in reason for reason in temp_validation_doc.reasons])

    # EDIFFG / force convergence check (this check should not raise any invalid reasons)
    temp_task_doc = copy.deepcopy(test_doc)
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert not any(["CONVERGENCE" in reason for reason in temp_validation_doc.reasons])


    # SIGMA too large check





    # raise ValueError(temp_validation_doc.reasons)



    # to be continued, starting with SIGMA too large check









### TODO: add tests for many other MP input sets (e.g. MPNSCFSet, MPNMRSet, MPScanRelaxSet, Hybrid sets, etc.)
    ### TODO: add ENAUG check for SCAN workflows
    ### TODO: add check for wrong ismear (e.g. -5) for metal relaxation
    ### TODO: add check for an MP input set that uses an IBRION other than [-1, 1, 2]
    ### TODO: add in second check for POTIM that checks for large energy changes between ionic steps
    ### TODO: add in energy-based EDIFFG check



