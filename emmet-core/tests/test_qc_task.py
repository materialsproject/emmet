import pytest

from emmet.core.testing_utils import assert_schemas_equal

from tests.conftest_qchem import get_test_object, OPENBABEL_INSTALLED


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
    if not OPENBABEL_INSTALLED:
        d.pop("custodian", None)
    MontyDecoder().process_decoded(d)

    # Test that additional_fields works
    test_doc = TaskDoc.from_directory(dir_name, additional_fields={"foo": "bar"})
    assert test_doc.model_dump()["additional_fields"] == {"foo": "bar"}


@pytest.mark.parametrize(
    "object_name",
    [
        pytest.param("SinglePointTest", id="SinglePointTest"),
        pytest.param("OptimizationTest", id="OptimizationTest"),
    ],
)
def test_task_doc_val_flag(test_dir, object_name):
    from monty.json import MontyDecoder, jsanitize
    from emmet.core.qc_tasks import TaskDoc

    test_object = get_test_object(object_name)
    dir_name = test_dir / "qchem" / test_object.folder
    test_doc = TaskDoc.from_directory(dir_name, validate_lot=False)
    assert_schemas_equal(test_doc, test_object.task_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    if not OPENBABEL_INSTALLED:
        d.pop("custodian", None)
    MontyDecoder().process_decoded(d)

    # Test that additional_fields works
    test_doc = TaskDoc.from_directory(
        dir_name, validate_lot=False, additional_fields={"foo": "bar"}
    )
    assert test_doc.model_dump()["additional_fields"] == {"foo": "bar"}


def test_custom_smd_solvation_lot(test_dir):
    """A custom SMD solvent ("solvent other") is read from the $smx section."""
    from emmet.core.qc_tasks import TaskDoc

    task_doc = TaskDoc.from_directory(test_dir / "qchem" / "qchem_custom_smd_sp_test")
    calc = task_doc.calcs_reversed[0]
    assert calc.solvation_lot_info == (
        "wB97M-V/def2-SVPD/SMD(DIELECTRIC=18,500;N=1,415;ALPHA=0,000;BETA=0,735;"
        "GAMMA=20,200;PHI=0,000;PSI=0,000)"
    )
    assert task_doc.output.final_energy == pytest.approx(-349.56285443)


def test_fragments_input(test_dir):
    """A $molecule section with fragments (here a fragment-based Hirshfeld CDFT
    calculation of Li+ and an ethylene carbonate radical anion) is parsed as one
    molecule with the total charge and spin multiplicity."""
    from emmet.core.io.pymatgen import QCInput
    from emmet.core.qc_tasks import TaskDoc
    from emmet.core.qchem.calculation import CalculationInput

    dir_name = test_dir / "qchem" / "qchem_cdft_fragments_sp_test"
    qcinput = QCInput.from_file(dir_name / "mol.qin.gz")
    assert isinstance(qcinput.molecule, list)
    assert [len(fragment) for fragment in qcinput.molecule] == [10, 1]

    input_doc = CalculationInput.from_qcinput(qcinput)
    molecule = input_doc.initial_molecule
    assert len(molecule) == 11
    assert (molecule.charge, molecule.spin_multiplicity) == (0, 2)
    assert input_doc.charge == 0
    assert molecule.cart_coords[:10] == pytest.approx(qcinput.molecule[0].cart_coords)

    task_doc = TaskDoc.from_directory(dir_name)
    assert task_doc.output.final_energy == pytest.approx(-349.52924705)
    output_molecule = task_doc.output.initial_molecule
    assert output_molecule.composition == molecule.composition
    assert (output_molecule.charge, output_molecule.spin_multiplicity) == (0, 2)


def test_input_with_molecule_read():
    """A $molecule section that reads the molecule from a previous job is
    still rejected."""
    from emmet.core.io.pymatgen import QCInput
    from emmet.core.qchem.calculation import CalculationInput

    qcinput = QCInput(
        molecule="read", rem={"job_type": "sp", "basis": "sto-3g", "method": "hf"}
    )
    with pytest.raises(ValueError, match="multiple molecules"):
        CalculationInput.from_qcinput(qcinput)
