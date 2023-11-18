from maggma.api.resource import HintScheme


class SummaryHintScheme(HintScheme):
    """
    Hint scheme for the summary endpoint.
    """

    def generate_hints(self, query):
        hints = {"count_hint": {"deprecated": 1, "builder_meta.license": 1}}
        hints["agg_hint"] = hints["count_hint"]

        if list(query.get("criteria").keys()) != ["deprecated", "builder_meta.license"]:
            pure_params = [param.split(".")[0] for param in query["criteria"]]

            if "has_props" in pure_params:
                hints["count_hint"] = {"has_props.$**": 1}
            elif "composition_reduced" in pure_params:
                hints["count_hint"] = {"composition_reduced.$**": 1}
            else:
                for param in query["criteria"]:
                    if param not in ["deprecated", "builder_meta.license"]:
                        hints["count_hint"] = {
                            "deprecated": 1,
                            "builder_meta.license": 1,
                            "formula_pretty": 1,
                            "material_id": 1,
                            param: 1,
                        }
                        break

            hints["agg_hint"] = hints["count_hint"]

        elif query.get("sort", {}):
            for param in query["sort"]:
                if param not in [
                    "deprecated",
                    "builder_meta.license",
                    "material_id",
                    "formula_pretty",
                ]:
                    hints["agg_hint"] = {
                        "deprecated": 1,
                        "builder_meta.license": 1,
                        "formula_pretty": 1,
                        "material_id": 1,
                        param: 1,
                    }

        return hints
