from copy import deepcopy
import json

import pytest
from monty.io import zopen

from emmet.core.tasks import TaskDoc
from emmet.core.vasp.calc_types import RunType, TaskType, run_type, task_type
from emmet.core.vasp.task_valid import TaskDocument
from emmet.core.vasp.validation import ValidationDoc, _potcar_stats_check


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
    with zopen(test_dir / "test_si_tasks.json.gz") as f:
        data = json.load(f)

    return [TaskDoc(**d) for d in data]


def test_validator(tasks):
    validation_docs = [ValidationDoc.from_task_doc(task) for task in tasks]

    assert len(validation_docs) == len(tasks)
    assert all([doc.valid for doc in validation_docs])


def test_validator_magmom(test_dir):
    # Task with Cr in structure - this is only element with MAGMOM check

    def cr_task_dict():
        # Model validation for TaskDoc serializes some fields.
        # Need to refresh reference unserialized dict to have
        # serialization for TaskDocument also work.
        with zopen(test_dir / "task_doc_mp-2766060.json.gz") as f:
            _cr_task_dict = json.load(f)
        return _cr_task_dict

    taskdoc = TaskDoc(**cr_task_dict())
    assert ValidationDoc.from_task_doc(taskdoc).valid

    # test backwards compatibility
    taskdocument = TaskDocument(
        **{k: v for k, v in cr_task_dict().items() if k != "last_updated"}
    )
    assert ValidationDoc.from_task_doc(taskdocument).valid

    # Change MAGMOM on Cr to fail magmom test
    td_bad_mag = TaskDoc(**cr_task_dict())
    td_bad_mag.calcs_reversed[0].output.outcar["magnetization"] = [
        {"tot": 6.0} if td_bad_mag.structure[ientry].species_string == "Cr" else entry
        for ientry, entry in enumerate(
            td_bad_mag.calcs_reversed[0].output.outcar["magnetization"]
        )
    ]
    assert not (valid_doc := ValidationDoc.from_task_doc(td_bad_mag)).valid
    assert any("MAG" in repr(reason) for reason in valid_doc.reasons)

    # Remove magnetization tag to simulate spin-unpolarized (ISPIN = 1) calculation
    td_no_mag = TaskDoc(**cr_task_dict())
    del td_no_mag.calcs_reversed[0].output.outcar["magnetization"]
    assert ValidationDoc.from_task_doc(td_no_mag).valid


def test_validator_failed_symmetry(test_dir):
    with zopen(test_dir / "failed_elastic_task.json.gz", "r") as f:
        failed_task = json.load(f)
    taskdoc = TaskDoc(**failed_task)
    validation = ValidationDoc.from_task_doc(taskdoc)
    assert any("SYMMETRY" in repr(reason) for reason in validation.reasons)


def test_computed_entry(tasks):
    entries = [task.entry for task in tasks]
    ids = {e.entry_id for e in entries}
    assert ids == {"mp-1141021", "mp-149", "mp-1686587", "mp-1440634"}


@pytest.fixture(scope="session")
def task_ldau(test_dir):
    with zopen(test_dir / "test_task.json") as f:
        data = json.load(f)

    return TaskDoc(**data)


def test_ldau(task_ldau):
    task_ldau.input.is_hubbard = True
    assert task_ldau.run_type == RunType.GGA_U
    assert not ValidationDoc.from_task_doc(task_ldau).valid


def test_ldau_validation(test_dir):
    with open(test_dir / "old_aflow_ggau_task.json") as f:
        data = json.load(f)

    task = TaskDoc(**data)
    assert task.run_type == "GGA+U"

    valid = ValidationDoc.from_task_doc(task)

    assert valid.valid


def test_potcar_stats_check(test_dir):
    from pymatgen.io.vasp import PotcarSingle

    with zopen(test_dir / "CoF_TaskDoc.json") as f:
        data = json.load(f)

    """
    NB: seems like TaskDoc is not fully compatible with TaskDocument
    excluding all keys but `last_updated` ensures TaskDocument can be built

    Similarly, after a TaskDoc is dumped to a file, using
        json.dump(
            jsanitize(
                < Task Doc >.model_dump()
            ),
        < filename > )
    I cannot rebuild the TaskDoc without excluding the `orig_inputs` key.
    """
    # task_doc = TaskDocument(**{key: data[key] for key in data if key != "last_updated"})
    task_doc = TaskDoc(**deepcopy(data))
    try:
        # First check: generate hashes from POTCARs in TaskDoc, check should pass
        calc_type = str(task_doc.calc_type)
        expected_hashes = {calc_type: {}}
        for spec in task_doc.calcs_reversed[0].input.potcar_spec:
            symbol = spec.titel.split(" ")[1]
            potcar = PotcarSingle.from_symbol_and_functional(
                symbol=symbol, functional="PBE"
            )
            expected_hashes[calc_type][symbol] = [
                {
                    **potcar._summary_stats,
                    "hash": potcar.md5_header_hash,
                    "titel": potcar.TITEL,
                }
            ]

        assert not _potcar_stats_check(task_doc, expected_hashes)

        # Second check: remove POTCAR from expected_hashes, check should fail

        missing_hashes = {calc_type: expected_hashes[calc_type].copy()}
        first_element = list(missing_hashes[calc_type])[0]
        missing_hashes[calc_type].pop(first_element)
        assert _potcar_stats_check(task_doc, missing_hashes)

        # Third check: change data in expected hashes, check should fail

        wrong_hashes = {calc_type: {**expected_hashes[calc_type]}}
        for key in wrong_hashes[calc_type][first_element][0]["stats"]["data"]:
            wrong_hashes[calc_type][first_element][0]["stats"]["data"][key] *= 1.1

        assert _potcar_stats_check(task_doc, wrong_hashes)

        # Fourth check: use legacy hash check if `summary_stats`
        # field not populated. This should pass
        legacy_data = deepcopy(data)
        legacy_data["calcs_reversed"][0]["input"]["potcar_spec"] = [
            {
                key: potcar[key]
                for key in (
                    "titel",
                    "hash",
                )
            }
            for potcar in legacy_data["calcs_reversed"][0]["input"]["potcar_spec"]
        ]
        legacy_task_doc = TaskDoc(
            **{key: legacy_data[key] for key in legacy_data if key != "last_updated"}
        )
        assert not _potcar_stats_check(legacy_task_doc, expected_hashes)

        # Fifth check: use legacy hash check if `summary_stats`
        # field not populated, but one hash is wrong. This should fail
        legacy_data = data.copy()
        legacy_data["calcs_reversed"][0]["input"]["potcar_spec"] = [
            {
                key: potcar[key]
                for key in (
                    "titel",
                    "hash",
                )
            }
            for potcar in legacy_data["calcs_reversed"][0]["input"]["potcar_spec"]
        ]
        legacy_data["calcs_reversed"][0]["input"]["potcar_spec"][0]["hash"] = (
            legacy_data["calcs_reversed"][0]["input"]["potcar_spec"][0]["hash"][:-1]
        )
        legacy_task_doc = TaskDoc(
            **{key: legacy_data[key] for key in legacy_data if key != "last_updated"}
        )
        assert _potcar_stats_check(legacy_task_doc, expected_hashes)

    except (OSError, ValueError):
        # missing Pymatgen POTCARs, cannot perform test
        assert True
