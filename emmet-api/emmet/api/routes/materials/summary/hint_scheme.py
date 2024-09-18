from maggma.api.resource import HintScheme


class SummaryHintScheme(HintScheme):
    """
    Hint scheme for the summary endpoint.
    """

    def generate_hints(self, query):
        hints = {"count_hint": {"deprecated": 1, "builder_meta.license": 1}}
        hints["agg_hint"] = hints["count_hint"]

        if list(query.get("criteria").keys()) != ["deprecated", "builder_meta.license"]:
            pure_params = []
            excluded_elements = False

            def check(val):
                sort_priority = {float: 0, int: 1, str: 2, bool: 3}

                if isinstance(val, dict):
                    val_list = list(val.values())
                    val = val_list[0] if val_list and val_list[0] else val

                return sort_priority.get(type(val), 100)

            sorted_raw_params = sorted(
                query["criteria"].items(),
                key=lambda x: check(x[1]),
            )

            for param, val in sorted_raw_params:
                pure_param = param.split(".")[0]
                pure_params.append(pure_param)
                if pure_param == "composition_reduced" and val == {"$exists": False}:
                    excluded_elements = True

            if "has_props" in pure_params:
                hints["count_hint"] = {"has_props.$**": 1}
            elif "composition_reduced" in pure_params and not excluded_elements:
                hints["count_hint"] = {"composition_reduced.$**": 1}
            else:
                for param, _ in sorted_raw_params:
                    if (
                        param not in ["deprecated", "builder_meta.license"]
                        and "composition_reduced" not in param
                    ):
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
