from maggma.api.resource import HintScheme


class MaterialsHintScheme(HintScheme):
    """
    Hint scheme for the materials endpoint.
    """

    def generate_hints(self, query):
        for param in query["criteria"]:
            if "composition_reduced" in param:
                return {"hint": {"composition_reduced.$**": 1}}
            elif "nelements" in param:
                return {"hint": {"nelements": 1}}

        return {"hint": {}}
