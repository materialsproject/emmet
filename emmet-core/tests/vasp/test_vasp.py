import json

import pytest
from monty.io import zopen

from emmet.core.mpid import AlphaID
from emmet.core.tasks import TaskDoc
from emmet.core.vasp.calc_types import RunType, TaskType, run_type, task_type
from emmet.core.vasp.validation import ValidationDoc
from emmet.core.vasp.validation_legacy import ValidationDoc as LegacyValidationDoc
from emmet.core.vasp.task_valid import TaskDocument
from emmet.core.testing_utils import DataArchive
from emmet.core.vasp.utils import discover_vasp_files

# As the validator itself is a separate package with its own tests,
# only check that its integration within emmet-core works.


def test_task_type():
    # TODO: Switch this to actual inputs?
    input_types = [
        ("NSCF Line", {"incar": {"ICHARG": 11}, "kpoints": {"labels": ["A"]}}),
        ("NSCF Uniform", {"incar": {"ICHARG": 11}}),
        ("Dielectric", {"incar": {"LEPSILON": True}}),
        ("DFPT Dielectric", {"incar": {"LEPSILON": True, "IBRION": 7}}),
        ("DFPT Dielectric", {"incar": {"LEPSILON": True, "IBRION": 8}}),
        ("DFPT", {"incar": {"IBRION": 7}}),
        ("DFPT", {"incar": {"IBRION": 8}}),
        ("Static", {"incar": {"NSW": 0}}),
    ]

    for _type, inputs in input_types:
        assert task_type(inputs) == TaskType(_type)


def test_run_type():
    params_sets = [
        ("GGA", {"GGA": "--"}),
        ("GGA+U", {"GGA": "--", "LDAU": True}),
        ("SCAN", {"METAGGA": "Scan"}),
        ("SCAN+U", {"METAGGA": "Scan", "LDAU": True}),
        ("r2SCAN", {"METAGGA": "R2SCAN"}),
        ("r2SCAN+U", {"METAGGA": "R2SCAN", "LDAU": True}),
        ("HFCus", {"LHFCALC": True}),
    ]

    for _type, params in params_sets:
        assert run_type(params) == RunType(_type)


@pytest.fixture(scope="session")
def tasks(test_dir):
    with zopen(test_dir / "test_si_tasks.json.gz", "rt") as f:
        data = json.load(f)

    return [TaskDoc(**d) for d in data]


def test_legacy_validator(tasks):
    validation_docs = [LegacyValidationDoc.from_task_doc(task) for task in tasks]

    assert len(validation_docs) == len(tasks)
    assert all([doc.valid for doc in validation_docs])


def test_legacy_validator_magmom(test_dir):
    # Task with Cr in structure - this is only element with MAGMOM check

    def cr_task_dict():
        # Model validation for TaskDoc serializes some fields.
        # Need to refresh reference unserialized dict to have
        # serialization for TaskDocument also work.
        with zopen(test_dir / "task_doc_mp-2766060.json.gz", "rt") as f:
            _cr_task_dict = json.load(f)
        return _cr_task_dict

    taskdoc = TaskDoc(**cr_task_dict())
    assert LegacyValidationDoc.from_task_doc(taskdoc).valid

    # test backwards compatibility
    taskdocument = TaskDocument(
        **{k: v for k, v in cr_task_dict().items() if k != "last_updated"}
    )
    assert LegacyValidationDoc.from_task_doc(taskdocument).valid

    # Change MAGMOM on Cr to fail magmom test
    td_bad_mag = TaskDoc(**cr_task_dict())
    td_bad_mag.calcs_reversed[0].output.outcar["magnetization"] = [
        {"tot": 6.0} if td_bad_mag.structure[ientry].species_string == "Cr" else entry
        for ientry, entry in enumerate(
            td_bad_mag.calcs_reversed[0].output.outcar["magnetization"]
        )
    ]
    assert not (valid_doc := LegacyValidationDoc.from_task_doc(td_bad_mag)).valid
    assert any("MAG" in repr(reason) for reason in valid_doc.reasons)

    # Remove magnetization tag to simulate spin-unpolarized (ISPIN = 1) calculation
    td_no_mag = TaskDoc(**cr_task_dict())
    del td_no_mag.calcs_reversed[0].output.outcar["magnetization"]
    assert LegacyValidationDoc.from_task_doc(td_no_mag).valid


def test_validator_failed_symmetry(test_dir):
    with zopen(test_dir / "failed_elastic_task.json.gz", "rt") as f:
        failed_task = json.load(f)
    taskdoc = TaskDoc(**failed_task)
    validation = LegacyValidationDoc.from_task_doc(taskdoc)
    assert any("SYMMETRY" in repr(reason) for reason in validation.reasons)


def test_computed_entry(tasks):
    entries = [task.entry for task in tasks]
    ids = {e.entry_id for e in entries}
    assert ids == set(
        [
            AlphaID(id_str).string
            for id_str in {"mp-ddzda", "mp-dryyt", "mp-cmxxl", "mp-ft"}
        ]
    )


@pytest.fixture(scope="session")
def task_ldau(test_dir):
    with zopen(test_dir / "test_task.json.gz", "rt") as f:
        data = json.load(f)

    return TaskDoc(**data)


def test_ldau(task_ldau):
    task_ldau.input.is_hubbard = True
    assert task_ldau.run_type == RunType.GGA_U
    assert not LegacyValidationDoc.from_task_doc(task_ldau).valid


def test_ldau_validation(test_dir):
    with zopen(test_dir / "old_aflow_ggau_task.json.gz", "rt") as f:
        data = json.load(f)

    task = TaskDoc(**data)
    assert task.run_type == "GGA+U"

    valid = LegacyValidationDoc.from_task_doc(task)

    assert valid.valid


def test_validator_integration(test_dir):
    calc_dirs = {
        "Si_old_double_relax": ["VASP VERSION"],
        "Si_uniform": [],
        "Si_static": [],
    }
    for calc_dir, ref_reasons in calc_dirs.items():
        with DataArchive.extract(test_dir / "vasp" / f"{calc_dir}.json.gz") as tmp_dir:
            task_doc = TaskDoc.from_directory(tmp_dir)
        valid_doc = ValidationDoc.from_task_doc(task_doc, check_potcar=False)
        if len(ref_reasons) == 0:
            assert valid_doc.valid
        else:
            assert not valid_doc.valid
            assert all(
                any(reason_match in reason for reason in valid_doc.reasons)
                for reason_match in ref_reasons
            )


def test_from_file_meta_and_dir(test_dir):
    with DataArchive.extract(test_dir / "vasp" / "Si_static.json.gz") as tmp_dir:
        files_by_suffix = discover_vasp_files(tmp_dir)

        valid_doc_from_meta = ValidationDoc.from_file_metadata(
            files_by_suffix["standard"], check_potcar=False
        )

        valid_doc_from_dir = ValidationDoc.from_directory(tmp_dir, check_potcar=False)

    assert valid_doc_from_meta.valid

    for k in ValidationDoc.model_fields:
        if k in {"last_updated", "builder_meta"}:
            # these contain time-stamped fields that won't match
            continue
        assert getattr(valid_doc_from_meta, k) == getattr(valid_doc_from_dir, k)
