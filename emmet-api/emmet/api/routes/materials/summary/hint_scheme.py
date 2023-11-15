from maggma.api.resource import HintScheme


class SummaryHintScheme(HintScheme):
    """
    Hint scheme for the summary endpoint.
    """

    def generate_hints(self, query):
        hints = {"count_hint": {"deprecated": 1, "builder_meta.license": 1}}
        hints["agg_hint"] = hints["count_hint"]

        if list(query.get("criteria").keys()) != ["deprecated", "builder_meta.license"]:
            for param in query["criteria"]:
                if (
                    param
                    not in [
                        "deprecated",
                        "builder_meta.license",
                    ]
                    and "has_props" not in param
                ):
                    hints["count_hint"] = {
                        "deprecated": 1,
                        "builder_meta.license": 1,
                        "formula_pretty": 1,
                        "material_id": 1,
                        param: 1,
                    }
                    hints["agg_hint"] = hints["count_hint"]
                    break

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
