import pytest
from tests.conftest import get_test_object

from emmet.core import ARROW_COMPATIBLE
from emmet.core.tasks import TaskDoc
from emmet.core.testing_utils import DataArchive, assert_schemas_equal
from emmet.core.vasp.task_valid import TaskState

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


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

    from emmet.core.tasks import AnalysisDoc, _get_state
    from emmet.core.vasp.calculation import Calculation

    test_object = get_test_object(object_name)

    with DataArchive.extract(
        test_dir / "vasp" / f"{test_object.folder}.json.gz"
    ) as dir_name:
        calcs_reversed = []
        for task_name, files in test_object.task_files.items():
            doc, _ = Calculation.from_vasp_files(dir_name, task_name, **files)
            calcs_reversed.append(doc)
            # The 2 tasks of double-relaxation have been reversed in
            # "/atomate2/tests/vasp/schemas/conftest.py" for "SiOptimizeDouble"
            # task_files are in the order of {"relax2","relax1"}

    test_doc = AnalysisDoc.from_vasp_calc_docs(calcs_reversed)
    assert _get_state(calcs_reversed, test_doc) == TaskState.SUCCESS
    valid_doc = test_object.task_doc["analysis"]
    assert_schemas_equal(test_doc, valid_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)


@pytest.mark.parametrize(
    ("object_name", "task_name"),
    [
        pytest.param("SiOptimizeDouble", "relax1", id="SiOptimizeDouble"),
        pytest.param("SiStatic", "standard", id="SiStatic"),
        pytest.param("SiNonSCFUniform", "standard", id="SiNonSCFUniform"),
    ],
)
def test_input_summary(test_dir, object_name, task_name):
    from monty.json import MontyDecoder, jsanitize

    from emmet.core.vasp.calculation import Calculation

    test_object = get_test_object(object_name)

    files = test_object.task_files[task_name]
    with DataArchive.extract(
        test_dir / "vasp" / f"{test_object.folder}.json.gz"
    ) as dir_name:
        calc_doc, _ = Calculation.from_vasp_files(dir_name, task_name, **files)

    test_doc = calc_doc.input
    valid_doc = test_object.task_doc["input"]
    assert_schemas_equal(test_doc, valid_doc)

    # test document can be jsanitized
    d = jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

    # and decoded
    MontyDecoder().process_decoded(d)


@pytest.mark.parametrize(
    ("object_name", "task_name"),
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

    files = test_object.task_files[task_name]
    with DataArchive.extract(
        test_dir / "vasp" / f"{test_object.folder}.json.gz"
    ) as dir_name:
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
def test_task_doc(test_dir, object_name, tmpdir):
    import os
    import shutil

    from monty.json import jsanitize
    from monty.serialization import dumpfn
    from pymatgen.alchemy.materials import TransformedStructure
    from pymatgen.entries.computed_entries import ComputedEntry
    from pymatgen.transformations.standard_transformations import (
        DeformStructureTransformation,
    )

    test_object = get_test_object(object_name)
    with DataArchive.extract(
        test_dir / "vasp" / f"{test_object.folder}.json.gz"
    ) as dir_name:
        test_doc = TaskDoc.from_directory(dir_name)

        assert_schemas_equal(test_doc, test_object.task_doc)

        # test document can be jsanitized
        jsanitize(test_doc, strict=True, enum_values=True, allow_bson=True)

        # This is currently an issue as older versions of dumped custodian VaspJob objects are in the
        # test files. This needs to be updated to properly test decoding.
        # MontyDecoder().process_decoded(dct)

        # Test that additional_fields works
        test_doc = TaskDoc.from_directory(dir_name, additional_fields={"foo": "bar"})

        assert test_doc.model_dump()["foo"] == "bar"

        assert len(test_doc.calcs_reversed) == len(test_object.task_files)
        assert test_doc.state == TaskState.SUCCESS

        # ensure that number of electronic steps are correctly populated
        for cr in test_doc.calcs_reversed:
            assert len(cr.output.ionic_steps) == len(cr.output.num_electronic_steps)
            assert cr.output.num_electronic_steps == [
                len(ionic_step.electronic_steps) for ionic_step in cr.output.ionic_steps
            ]

        # ensure that run stats are not all identically zero (i.e., they are parsed correctly)
        for run_stats in test_doc.run_stats.values():
            assert any(abs(time) > 1e-6 for time in run_stats.model_dump().values())

        # Check that entry is populated when calcs_reversed is not None
        if test_doc.calcs_reversed:
            assert isinstance(
                test_doc.entry, ComputedEntry
            ), f"Unexpected entry {test_doc.entry} for {object_name}"

        # Test that transformations field works, using hydrostatic compression as example
        ts = TransformedStructure(
            test_doc.output.structure,
            transformations=[
                DeformStructureTransformation(
                    deformation=[
                        [0.9 if i == j else 0.0 for j in range(3)] for i in range(3)
                    ]
                )
            ],
        )
        ts_json = jsanitize(ts.as_dict())
        dumpfn(ts, f"{tmpdir}/transformations.json")
        for f in os.listdir(dir_name):
            if os.path.isfile(os.path.join(dir_name, f)):
                shutil.copy(os.path.join(dir_name, f), tmpdir)
        test_doc = TaskDoc.from_directory(tmpdir)
    # if other_parameters == {}, this is popped from the TaskDoc.transformations field
    # seems like @version is added by monty serialization
    # jsanitize needed because pymatgen.core.Structure.pbc is a tuple
    assert all(
        test_doc.transformations[k] == v
        for k, v in ts_json.items()
        if k
        not in (
            "other_parameters",
            "@version",
            "last_modified",
        )
    )
    assert isinstance(test_doc.transformations, dict)

    # now test case when transformations are serialized, relevant for atomate2
    test_doc = TaskDoc(
        **{
            "transformations": ts,
            **{
                k: v for k, v in test_doc.model_dump().items() if k != "transformations"
            },
        }
    )
    assert all(
        test_doc.transformations[k] == v
        for k, v in ts.as_dict().items()
        if k != "last_modified"
    )


def test_lda_and_pseudo_format(test_dir, tmpdir):

    from emmet.core.tasks import TaskDoc

    with DataArchive.extract(
        test_dir / "vasp" / "lda_calc.json.gz",
    ) as dir_name:
        task = TaskDoc.from_directory(dir_name)

    assert task.run_type.name == "LDA"
    assert all(task.input.incar.get(k) is None for k in ("GGA", "METAGGA"))

    expected_pseudo = {
        "pot_type": "PAW",
        "functional": "LDA",
        "symbols": ["Si"],
    }

    assert all(
        getattr(task.input.pseudo_potentials, k) == v
        for k, v in expected_pseudo.items()
    )


def test_orig_inp_parsing(tmp_dir):
    """Test parsing of VASP input with variable suffix, like `.orig`."""

    from pathlib import Path

    from pymatgen.core import Structure
    from pymatgen.io.vasp import Incar, Kpoints

    from emmet.core.tasks import _parse_orig_inputs

    # demo simple cubic Copper structure
    structure = Structure(
        [[3 if i != j else 0.0 for j in range(3)] for i in range(3)],
        ["Cu"],
        [[0.0, 0.0, 0.0]],
    )

    incar = Incar.from_dict(
        {
            "ALGO": "Normal",
            "ENCUT": 600,
        }
    )
    kpoints = Kpoints()

    for suffix in (".orig", ".image", ".mangoes"):
        structure.to(f"POSCAR{suffix}")
        incar.write_file(f"INCAR{suffix}")
        kpoints.write_file(f"KPOINTS{suffix}")

        vi = _parse_orig_inputs(Path("."), suffix=suffix)
        assert all(k in vi for k in ("incar", "kpoints", "poscar"))
        assert len(vi) == 3


@pytest.mark.parametrize(
    "object_name",
    [
        pytest.param("SiOptimizeDouble", id="SiOptimizeDouble"),
        pytest.param("SiStatic", id="SiStatic"),
        pytest.param("SiNonSCFUniform", id="SiNonSCFUniform"),
    ],
)
@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow(test_dir, object_name, tmpdir):
    test_object = get_test_object(object_name)

    with DataArchive.extract(
        test_dir / "vasp" / f"{test_object.folder}.json.gz"
    ) as dir_name:

        doc = TaskDoc.from_directory(dir_name)
        arrow_struct = pa.scalar(
            doc.model_dump(context={"format": "arrow"}), type=arrowize(TaskDoc)
        )

        # Avoiding comparisons of round tripped arrow doc vs. original doc
        # due to a few field types that get changed during json serialization
        # e.g., orig_inputs/input.kpoints.tet_weight is a float, but if the
        # val is 0 json dumps to int -> 0, 0 != 0.0 when comparing doc models
        # TBD on the value of getting this strict comparison correct

        assert TaskDoc(**arrow_struct.as_py(maps_as_pydicts="strict"))
