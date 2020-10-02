from emmet.core.vasp.calc_types import run_type, task_type, RunType, TaskType


def test_task_tye():

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
    ]

    for _type, params in params_sets:
        assert run_type(params) == RunType(_type)