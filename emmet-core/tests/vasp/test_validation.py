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

    # NBANDS too high check
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
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.calcs_reversed[0].output.ionic_steps[0].electronic_steps[-1].eentropy = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["SIGMA: The entropy term (T*S)" in reason for reason in temp_validation_doc.reasons])

    # LMAXMIX check for SCF calc
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LMAXMIX"] = 0
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    # should not invalidate SCF calcs based on LMAXMIX
    assert not any(["LMAXMIX" in reason for reason in temp_validation_doc.reasons])
    # rather should add a warning
    assert any(["LMAXMIX" in warning for warning in temp_validation_doc.warnings])

    # LNONCOLLINEAR check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LNONCOLLINEAR"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LNONCOLLINEAR" in reason for reason in temp_validation_doc.reasons])

    # LSORBIT check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LSORBIT"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LSORBIT" in reason for reason in temp_validation_doc.reasons])

    # LSORBIT check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LSORBIT"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LSORBIT" in reason for reason in temp_validation_doc.reasons])

    # DEPER check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["DEPER"] = 0.5
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["DEPER" in reason for reason in temp_validation_doc.reasons])

    # EBREAK check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["EBREAK"] = 0.1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["EBREAK" in reason for reason in temp_validation_doc.reasons])

    # GGA_COMPAT check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["GGA_COMPAT"] = False
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["GGA_COMPAT" in reason for reason in temp_validation_doc.reasons])

    # ICORELEVEL check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ICORELEVEL"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ICORELEVEL" in reason for reason in temp_validation_doc.reasons])

    # IMAGES check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["IMAGES"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["IMAGES" in reason for reason in temp_validation_doc.reasons])

    # IVDW check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["IVDW"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["IVDW" in reason for reason in temp_validation_doc.reasons])

    # LBERRY check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LBERRY"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LBERRY" in reason for reason in temp_validation_doc.reasons])

    # LCALCEPS check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LCALCEPS"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LCALCEPS" in reason for reason in temp_validation_doc.reasons])

    # LCALCPOL check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LCALCPOL"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LCALCPOL" in reason for reason in temp_validation_doc.reasons])

    # LHYPERFINE check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LHYPERFINE"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LHYPERFINE" in reason for reason in temp_validation_doc.reasons])

    # LKPOINTS_OPT check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LKPOINTS_OPT"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LKPOINTS_OPT" in reason for reason in temp_validation_doc.reasons])

    # LKPROJ check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LKPROJ"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LKPROJ" in reason for reason in temp_validation_doc.reasons])

    # LMP2LT check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LMP2LT"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LMP2LT" in reason for reason in temp_validation_doc.reasons])

    # LOCPROJ check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LOCPROJ"] = "1 : s : Hy"
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LOCPROJ" in reason for reason in temp_validation_doc.reasons])

    # LRPA check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LRPA"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LRPA" in reason for reason in temp_validation_doc.reasons])

    # LSMP2LT check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LSMP2LT"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LSMP2LT" in reason for reason in temp_validation_doc.reasons])

    # LSPECTRAL check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LSPECTRAL"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LSPECTRAL" in reason for reason in temp_validation_doc.reasons])

    # LSUBROT check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LSUBROT"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LSUBROT" in reason for reason in temp_validation_doc.reasons])

    # ML_LMLFF check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ML_LMLFF"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ML_LMLFF" in reason for reason in temp_validation_doc.reasons])

    # WEIMIN check too high (invalid)
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["WEIMIN"] = 0.01
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["WEIMIN" in reason for reason in temp_validation_doc.reasons])

    # WEIMIN check too low (valid)
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["WEIMIN"] = 0.0001
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert not any(["WEIMIN" in reason for reason in temp_validation_doc.reasons])

    # EFERMI check (does not matter for VASP versions before 6.4)
    # must check EFERMI in the *incar*, as it is saved as a numerical value after VASP 
    # guesses it in the vasprun.xml `parameters`
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.calcs_reversed[0].vasp_version = "5.4.4"
    temp_task_doc.calcs_reversed[0].input.incar["EFERMI"] = 5
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert not any(["EFERMI" in reason for reason in temp_validation_doc.reasons])

    # EFERMI check (matters for VASP versions 6.4 and beyond)
    # must check EFERMI in the *incar*, as it is saved as a numerical value after VASP
    # guesses it in the vasprun.xml `parameters`
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.calcs_reversed[0].vasp_version = "6.4.0"
    temp_task_doc.calcs_reversed[0].input.incar["EFERMI"] = 5
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["EFERMI" in reason for reason in temp_validation_doc.reasons])

    # IWAVPR check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.calcs_reversed[0].input.incar["IWAVPR"] = 1
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["IWAVPR" in reason for reason in temp_validation_doc.reasons])

    # LASPH check too low (valid)
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LASPH"] = False
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LASPH" in reason for reason in temp_validation_doc.reasons])

    # LCORR check (checked when IALGO != 58) (should be invalid in this case)
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["IALGO"] = 38
    temp_task_doc.input.parameters["LCORR"] = False
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LCORR" in reason for reason in temp_validation_doc.reasons])

    # LCORR check (checked when IALGO != 58) (should be valid in this case)
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["IALGO"] = 58
    temp_task_doc.input.parameters["LCORR"] = False
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert not any(["LCORR" in reason for reason in temp_validation_doc.reasons])

    # LORBIT check (should have magnetization values for ISPIN=2)
    # Should be valid for this case, as no magmoms are expected for ISPIN = 1
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISPIN"] = 1
    temp_task_doc.calcs_reversed[0].output.outcar["magnetization"] = []
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert not any(["LORBIT" in reason for reason in temp_validation_doc.reasons])

    # LORBIT check (should have magnetization values for ISPIN=2)
    # Should be valid in this case, as magmoms are present for ISPIN = 2
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISPIN"] = 2
    temp_task_doc.calcs_reversed[0].output.outcar["magnetization"] = (
        {'s': -0.0, 'p': 0.0, 'd': 0.0, 'tot': 0.0}, 
        {'s': -0.0, 'p': 0.0, 'd': 0.0, 'tot': -0.0}
    )
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert not any(["LORBIT" in reason for reason in temp_validation_doc.reasons])

    # LORBIT check (should have magnetization values for ISPIN=2)
    # Should be invalid in this case, as no magmoms are present for ISPIN = 2
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISPIN"] = 2
    temp_task_doc.calcs_reversed[0].output.outcar["magnetization"] = []
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LORBIT" in reason for reason in temp_validation_doc.reasons])

    # RWIGS check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["RWIGS"] = [1]
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["RWIGS" in reason for reason in temp_validation_doc.reasons])

    # VCA check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["VCA"] = [0.5]
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["VCA" in reason for reason in temp_validation_doc.reasons])

    # PREC check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["PREC"] = "NORMAL"
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["PREC" in reason for reason in temp_validation_doc.reasons])

    # ROPT check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ROPT"] = [-0.001]
    temp_task_doc.input.parameters["LREAL"] = True
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ROPT" in reason for reason in temp_validation_doc.reasons])

    # ICHARG check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ICHARG"] = 11
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ICHARG" in reason for reason in temp_validation_doc.reasons])

    # INIWAV check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["INIWAV"] = 0
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["INIWAV" in reason for reason in temp_validation_doc.reasons])

    # ISTART check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISTART"] = 3
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ISTART" in reason for reason in temp_validation_doc.reasons])

    # ISYM check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["ISYM"] = 3
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["ISYM" in reason for reason in temp_validation_doc.reasons])

    # SYMPREC check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["SYMPREC"] = 1e-2
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["SYMPREC" in reason for reason in temp_validation_doc.reasons])

    # LDAUU check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LDAU"] = True
    temp_task_doc.input.parameters["LDAUU"] = [5, 5]
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LDAUU" in reason for reason in temp_validation_doc.reasons])

    # LDAUJ check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LDAU"] = True
    temp_task_doc.input.parameters["LDAUJ"] = [5, 5]
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LDAUJ" in reason for reason in temp_validation_doc.reasons])

    # LDAUL check
    temp_task_doc = copy.deepcopy(test_doc)
    temp_task_doc.input.parameters["LDAU"] = True
    temp_task_doc.input.parameters["LDAUL"] = [5, 5]
    temp_validation_doc = ValidationDoc.from_task_doc(temp_task_doc)
    assert any(["LDAUL" in reason for reason in temp_validation_doc.reasons])

    # print(temp_task_doc.calcs_reversed[0].input.incar.get("LDAUU"))
    # blah


    # print(temp_validation_doc.reasons)
    # # print(temp_validation_doc.warnings)
    # blah_error_please











### TODO: add tests for many other MP input sets (e.g. MPNSCFSet, MPNMRSet, MPScanRelaxSet, Hybrid sets, etc.)
    ### TODO: add ENAUG check for SCAN workflows
    ### TODO: add check for wrong ismear (e.g. -5) for metal relaxation
    ### TODO: add check for an MP input set that uses an IBRION other than [-1, 1, 2]
    ### TODO: add in second check for POTIM that checks for large energy changes between ionic steps
    ### TODO: add in energy-based EDIFFG check
    ### TODO: add in an LMAXMIX check for NSCF calcs
    ### TODO: add in an LMAXTAU check for SCF and NSCF calcs (need METAGGA calcs)



