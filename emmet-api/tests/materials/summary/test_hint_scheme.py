from emmet.api.routes.materials.summary.hint_scheme import SummaryHintScheme


def test_summary_hint_scheme():
    scheme = SummaryHintScheme()
    assert scheme.generate_hints(
        {
            "criteria": {
                "deprecated": 1,
                "builder_meta.license": "BY-C",
                "nelements": 3,
            },
            "sort": {"energy_above_hull": 1},
        }
    ) == {
        "count_hint": {
            "deprecated": 1,
            "builder_meta.license": 1,
            "formula_pretty": 1,
            "material_id": 1,
            "nelements": 1,
        },
        "agg_hint": {
            "deprecated": 1,
            "builder_meta.license": 1,
            "formula_pretty": 1,
            "material_id": 1,
            "nelements": 1,
        },
    }
    assert scheme.generate_hints(
        {
            "criteria": {
                "deprecated": 1,
                "builder_meta.license": "BY-C",
                "has_props": "dos",
            },
            "sort": {"energy_above_hull": 1},
        }
    ) == {
        "count_hint": {"has_props.$**": 1},
        "agg_hint": {"has_props.$**": 1},
    }
    assert scheme.generate_hints(
        {
            "criteria": {"deprecated": 1, "builder_meta.license": "BY-C"},
            "sort": {"energy_above_hull": 1},
        }
    ) == {
        "count_hint": {"deprecated": 1, "builder_meta.license": 1},
        "agg_hint": {
            "deprecated": 1,
            "builder_meta.license": 1,
            "formula_pretty": 1,
            "material_id": 1,
            "energy_above_hull": 1,
        },
    }
