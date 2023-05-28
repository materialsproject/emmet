from emmet.api.routes.molecules.molecules.hint_scheme import MoleculesHintScheme


def test_task_hint_scheme():
    scheme = MoleculesHintScheme()
    assert scheme.generate_hints(
        {"criteria": {"composition": {"Li": 2, "C": 1, "O": 3}}}
    ) == {"hint": {"composition.$**": 1}}
