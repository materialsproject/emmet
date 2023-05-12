from emmet.api.routes.molecules.tasks.hint_scheme import TasksHintScheme


def test_task_hint_scheme():
    scheme = TasksHintScheme()
    assert scheme.generate_hints(
        {"criteria": {"composition": {"Li": 2, "C": 1, "O": 3}}}
    ) == {"hint": {"composition.$**": 1}}
