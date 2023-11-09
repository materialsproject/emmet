from maggma.api.resource import HintScheme


class MaterialsHintScheme(HintScheme):
    """
    Hint scheme for the materials endpoint.
    """

    def generate_hints(self, query):
        hints = {"count_hint": {"deprecated": 1, "builder_meta.license": 1}}
    
        for param in query["criteria"]:
            if "nelements" in param:
                hints["count_hint"]= {"nelements": 1}

        hints["agg_hint"] = hints["count_hint"]
        return hints