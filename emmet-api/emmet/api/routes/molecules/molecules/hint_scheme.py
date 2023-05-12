from maggma.api.resource import HintScheme


class MoleculesHintScheme(HintScheme):
    """
    Hint scheme for the molecules/molecules endpoint.
    """

    def generate_hints(self, query):
        for param in query["criteria"]:
            if "composition" in param:
                return {"hint": {"composition.$**": 1}}

        return {"hint": {}}
