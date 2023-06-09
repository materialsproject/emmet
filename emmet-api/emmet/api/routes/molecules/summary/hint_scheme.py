from maggma.api.resource import HintScheme


class SummaryHintScheme(HintScheme):
    """
    Hint scheme for the molecules/summary endpoint.
    """

    def generate_hints(self, query):
        for param in query["criteria"]:
            if "composition" in param:
                return {"hint": {"composition.$**": 1}}

        return {"hint": {}}
