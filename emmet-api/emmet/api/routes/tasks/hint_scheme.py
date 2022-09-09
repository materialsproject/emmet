from maggma.api.resource import HintScheme


class TasksHintScheme(HintScheme):
    """
    Hint scheme for the tasks endpoint.
    """

    def generate_hints(self, query):

        if query["criteria"] == {}:
            return {"hint": {"_id": 1}}

        for param in query["criteria"]:

            if "composition_reduced" in param:
                return {"hint": {"composition_reduced.$**": 1}}
            elif "nelements" in param:
                return {"hint": {"nelements": 1}}

        return {"hint": {}}
