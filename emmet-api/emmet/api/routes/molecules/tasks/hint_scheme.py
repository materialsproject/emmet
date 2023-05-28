from maggma.api.resource import HintScheme


class TasksHintScheme(HintScheme):
    """
    Hint scheme for the molecules/tasks endpoint.
    """

    def generate_hints(self, query):
        if query["criteria"] == {}:
            return {"hint": {"_id": 1}}

        for param in query["criteria"]:
            if "composition" in param:
                return {"hint": {"composition.$**": 1}}

        return {"hint": {}}
