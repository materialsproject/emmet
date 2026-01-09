import pytest

from emmet.core.testing_utils import assert_schemas_equal, DataArchive
from tests.conftest import get_test_object


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

    with DataArchive.extract(
        test_dir / "vasp" / f"{test_object.folder}.json.gz"
    ) as dir_name:
        vasprun_file = dir_name / test_object.task_files[task_name]["vasprun_file"]
        test_doc = CalculationInput.from_vasprun(Vasprun(vasprun_file))
        valid_doc = test_object.task_doc["calcs_reversed"][0]["input"]
    assert_schemas_equal(test_doc, valid_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)

    # Test hubbard U re-parsing
    test_doc_dct = test_doc.model_dump()
    hubbards = list(range(1, 1 + len(test_doc.structure.composition.elements)))
    test_doc_dct["incar"]["LDAU"] = True
    test_doc_dct["incar"]["LDAUU"] = hubbards
    test_doc_dct["is_hubbard"] = True
    test_doc_dct.pop("hubbards", None)
    hubbard_doc = CalculationInput(**test_doc_dct)
    assert hubbard_doc.is_hubbard
    assert hubbard_doc.hubbards == {
        ele: hubbards[i] for i, ele in enumerate(hubbard_doc.potcar)
    }


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
    with DataArchive.extract(
        test_dir / "vasp" / f"{test_object.folder}.json.gz"
    ) as dir_name:
        vasprun = Vasprun(dir_name / test_object.task_files[task_name]["vasprun_file"])
        outcar = Outcar(dir_name / test_object.task_files[task_name]["outcar_file"])
        contcar = Poscar.from_file(
            dir_name / test_object.task_files[task_name]["contcar_file"]
        )
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
    with DataArchive.extract(test_dir / "vasp" / "magnetic_run.json.gz") as dir_name:
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

    outcar = DataArchive.extract_obj(
        test_dir / "vasp" / f"{test_object.folder}.json.gz",
        test_object.task_files[task_name]["outcar_file"],
        Outcar,
    )
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
    files = test_object.task_files[task_name]

    with DataArchive.extract(
        test_dir / "vasp" / f"{test_object.folder}.json.gz"
    ) as dir_name:

        test_doc, objects = Calculation.from_vasp_files(dir_name, task_name, **files)
    valid_doc = test_object.task_doc["calcs_reversed"][0]
    assert_schemas_equal(test_doc, valid_doc)
    assert set(objects.keys()) == set(test_object.objects[task_name])

    # check bader and ddec6 keys exist
    assert test_doc.bader is None
    assert test_doc.ddec6 is None

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)


@pytest.mark.parametrize("use_emmet_models", [True, False])
def test_calculation_run_type_metagga(test_dir, use_emmet_models):
    # Test to ensure that meta-GGA calculations are correctly identified
    # The VASP files were kindly provided by @Andrew-S-Rosen in issue #960
    import numpy as np

    from emmet.core.vasp.calculation import Calculation
    from emmet.core.tasks import OutputDoc

    with DataArchive.extract(test_dir / "vasp" / "r2scan_relax.json.gz") as dir_name:
        calc, vasp_objects = Calculation.from_vasp_files(
            dir_name=dir_name,
            task_name="relax",
            vasprun_file="vasprun.xml.gz",
            outcar_file="OUTCAR.gz",
            contcar_file="CONTCAR.gz",
            parse_bandstructure=True,
            parse_dos=True,
            store_trajectory="full",
            use_emmet_models=use_emmet_models,
        )
    assert "r2SCAN" in repr(calc.run_type)
    assert "r2SCAN" in repr(calc.calc_type)

    if use_emmet_models:
        from emmet.core.trajectory import RelaxTrajectory
        from emmet.core.band_theory import ElectronicBS, ElectronicDos

        assert isinstance(vasp_objects["trajectory"], RelaxTrajectory)
        assert isinstance(vasp_objects["bandstructure"], ElectronicBS)
        assert isinstance(vasp_objects["dos"], ElectronicDos)

    else:
        from pymatgen.core.trajectory import Trajectory
        from pymatgen.electronic_structure.bandstructure import BandStructure
        from pymatgen.electronic_structure.dos import CompleteDos

        assert isinstance(vasp_objects["trajectory"], Trajectory)
        assert isinstance(vasp_objects["bandstructure"], BandStructure)
        assert isinstance(vasp_objects["dos"], CompleteDos)

    # ensure parsing of forces and stress from trajectory rather than
    # ionic steps works correctly regardless of models used
    calc.output.ionic_steps = None
    output_calc = OutputDoc.from_vasp_calc_doc(
        calc, trajectory=vasp_objects["trajectory"]
    )
    for k in ("forces", "stress"):
        assert np.allclose(
            getattr(output_calc, k),
            (
                getattr(vasp_objects["trajectory"], k)[-1]
                if use_emmet_models
                else vasp_objects["trajectory"].frame_properties[-1].get(k)
            ),
        )


def test_PotcarSpec(test_dir):
    from emmet.core.vasp.calculation import PotcarSpec
    from pymatgen.io.vasp import PotcarSingle, Potcar

    try:
        # First test, PotcarSingle object
        potcar = PotcarSingle.from_symbol_and_functional(symbol="Si", functional="PBE")
        ps_spec = PotcarSpec.from_potcar_single(potcar_single=potcar)

        assert ps_spec.titel.split("")[1] == potcar.symbol
        assert ps_spec.hash == potcar.md5_header_hash
        assert ps_spec.summary_stats == potcar._summary_stats

        # Second test, Potcar object containing mulitple PotcarSingle obejcts
        potcars = Potcar(symbols=["Ga_d", "As"], functional="PBE")
        ps_spec = PotcarSpec.from_potcar(potcar=potcars)

        for ips, ps in enumerate(ps_spec):
            assert ps.titel == potcars[ips].symbol
            assert ps.hash == potcars[ips].md5_header_hash
            assert ps.summary_stats == potcars[ips]._summary_stats

    except (OSError, ValueError):
        # missing Pymatgen POTCARs, cannot perform test
        assert True
