import pytest
from tests.conftest import assert_schemas_equal, get_test_object


def test_init():
    from emmet.core.vasp.calculation import (
        Calculation,
        CalculationInput,
        CalculationOutput,
        RunStatistics,
    )

    calc_input = CalculationInput()
    assert calc_input is not None

    calc_input = CalculationOutput()
    assert calc_input is not None

    calc_input = RunStatistics()
    assert calc_input is not None

    calc_input = Calculation()
    assert calc_input is not None


@pytest.mark.parametrize(
    "object_name,task_name",
    [
        pytest.param("SiOptimizeDouble", "relax1", id="SiOptimizeDouble"),
        pytest.param("SiStatic", "standard", id="SiStatic"),
        pytest.param("SiNonSCFUniform", "standard", id="SiNonSCFUniform"),
    ],
)
def test_calculation_input(test_dir, object_name, task_name):
    from monty.json import MontyDecoder, jsanitize
    from pymatgen.io.vasp import Vasprun

    from emmet.core.vasp.calculation import CalculationInput

    test_object = get_test_object(object_name)
    vasprun_file = test_dir / "vasp" / test_object.folder
    vasprun_file /= test_object.task_files[task_name]["vasprun_file"]
    test_doc = CalculationInput.from_vasprun(Vasprun(vasprun_file))
    valid_doc = test_object.task_doc["calcs_reversed"][0]["input"]
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
def test_calculation_output(test_dir, object_name, task_name):
    from monty.json import MontyDecoder, jsanitize
    from pymatgen.io.vasp import Outcar, Poscar, Vasprun

    from emmet.core.vasp.calculation import CalculationOutput

    test_object = get_test_object(object_name)
    folder = test_dir / "vasp" / test_object.folder
    vasprun_file = folder / test_object.task_files[task_name]["vasprun_file"]
    outcar_file = folder / test_object.task_files[task_name]["outcar_file"]
    contcar_file = folder / test_object.task_files[task_name]["contcar_file"]
    vasprun = Vasprun(vasprun_file)
    outcar = Outcar(outcar_file)
    contcar = Poscar.from_file(contcar_file)
    test_doc = CalculationOutput.from_vasp_outputs(vasprun, outcar, contcar)
    valid_doc = test_object.task_doc["calcs_reversed"][0]["output"]
    assert_schemas_equal(test_doc, valid_doc)
    assert test_doc.efermi == vasprun.get_band_structure(efermi="smart").efermi

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)


def test_mag_calculation_output(test_dir):
    from pymatgen.io.vasp import Outcar, Poscar, Vasprun

    from emmet.core.vasp.calculation import CalculationOutput

    # Test magnetic properties
    dir_name = test_dir / "vasp" / "magnetic_run"
    d = CalculationOutput.from_vasp_outputs(
        Vasprun(dir_name / "vasprun.xml.gz"),
        Outcar(dir_name / "OUTCAR.gz"),
        Poscar.from_file(dir_name / "CONTCAR.gz"),
    )
    assert d.model_dump()["mag_density"] == pytest.approx(0.19384725901794095)


@pytest.mark.parametrize(
    "object_name,task_name",
    [
        pytest.param("SiOptimizeDouble", "relax1", id="SiOptimizeDouble"),
        pytest.param("SiStatic", "standard", id="SiStatic"),
        pytest.param("SiNonSCFUniform", "standard", id="SiNonSCFUniform"),
    ],
)
def test_run_statistics(test_dir, object_name, task_name):
    from monty.json import MontyDecoder, jsanitize
    from pymatgen.io.vasp import Outcar

    from emmet.core.vasp.calculation import RunStatistics

    test_object = get_test_object(object_name)
    folder = test_dir / "vasp" / test_object.folder
    outcar_file = folder / test_object.task_files[task_name]["outcar_file"]
    outcar = Outcar(outcar_file)
    test_doc = RunStatistics.from_outcar(outcar)
    valid_doc = test_object.task_doc["calcs_reversed"][0]["output"]["run_stats"]
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
def test_calculation(test_dir, object_name, task_name):
    from monty.json import MontyDecoder, jsanitize

    from emmet.core.vasp.calculation import Calculation

    test_object = get_test_object(object_name)
    dir_name = test_dir / "vasp" / test_object.folder
    files = test_object.task_files[task_name]

    test_doc, objects = Calculation.from_vasp_files(dir_name, task_name, **files)
    valid_doc = test_object.task_doc["calcs_reversed"][0]
    assert_schemas_equal(test_doc, valid_doc)
    assert set(objects.keys()) == set(test_object.objects[task_name])

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)
