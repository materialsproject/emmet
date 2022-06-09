from emmet.api.routes.synthesis.query_operators import SynthesisSearchQuery
from emmet.core.synthesis import SynthesisTypeEnum, OperationTypeEnum

from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


def test_synthesis_search_query():
    op = SynthesisSearchQuery()
    keyword_lists = [None, "silicon, process"]

    for keywords in keyword_lists:
        pipeline = (
            [
                {
                    "$match": {
                        "synthesis_type": {"$in": ["solid-state"]},
                        "targets_formula_s": "SiO2",
                        "precursors_formula_s": "SiO2",
                        "operations.type": {"$all": ["ShapingOperation"]},
                        "operations.conditions.heating_temperature.values": {
                            "$elemMatch": {"$gte": 0, "$lte": 5}
                        },
                        "operations.conditions.heating_time.values": {
                            "$elemMatch": {"$gte": 0, "$lte": 5}
                        },
                        "operations.conditions.heating_atmosphere": {"$all": ["air"]},
                        "operations.conditions.mixing_device": {"$all": ["zirconia"]},
                        "operations.conditions.mixing_media": {"$all": ["water"]},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "doi": 1,
                        "synthesis_type": 1,
                        "reaction": 1,
                        "reaction_string": 1,
                        "operations": 1,
                        "target": 1,
                        "targets_formula": 1,
                        "targets_formula_s": 1,
                        "precursors": 1,
                        "precursors_formula_s": 1,
                        "paragraph_string": 1,
                    }
                },
                {
                    "$facet": {
                        "results": [{"$skip": 0}, {"$limit": 10}],
                        "total_doc": [{"$count": "count"}],
                    }
                },
                {"$unwind": "$results"},
                {"$unwind": "$total_doc"},
                {
                    "$replaceRoot": {
                        "newRoot": {
                            "$mergeObjects": [
                                "$results",
                                {"total_doc": "$total_doc.count"},
                            ]
                        }
                    }
                },
            ]
            if keywords is None
            else [
                {
                    "$search": {
                        "index": "synth_descriptions",
                        "search": {
                            "query": ["silicon", "process"],
                            "path": "paragraph_string",
                        },
                        "highlight": {"path": "paragraph_string"},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "doi": 1,
                        "highlights": {"$meta": "searchHighlights"},
                        "synthesis_type": 1,
                        "reaction": 1,
                        "reaction_string": 1,
                        "search_score": {"$meta": "searchScore"},
                        "operations": 1,
                        "target": 1,
                        "targets_formula": 1,
                        "targets_formula_s": 1,
                        "precursors": 1,
                        "precursors_formula_s": 1,
                        "paragraph_string": 1,
                    }
                },
                {
                    "$match": {
                        "synthesis_type": {"$in": ["solid-state"]},
                        "targets_formula_s": "SiO2",
                        "precursors_formula_s": "SiO2",
                        "operations.type": {"$all": ["ShapingOperation"]},
                        "operations.conditions.heating_temperature.values": {
                            "$elemMatch": {"$gte": 0, "$lte": 5}
                        },
                        "operations.conditions.heating_time.values": {
                            "$elemMatch": {"$gte": 0, "$lte": 5}
                        },
                        "operations.conditions.heating_atmosphere": {"$all": ["air"]},
                        "operations.conditions.mixing_device": {"$all": ["zirconia"]},
                        "operations.conditions.mixing_media": {"$all": ["water"]},
                    }
                },
                {
                    "$facet": {
                        "results": [
                            {"$sort": {"search_score": -1}},
                            {"$skip": 0},
                            {"$limit": 10},
                        ],
                        "total_doc": [{"$count": "count"}],
                    }
                },
                {"$unwind": "$results"},
                {"$unwind": "$total_doc"},
                {
                    "$replaceRoot": {
                        "newRoot": {
                            "$mergeObjects": [
                                "$results",
                                {"total_doc": "$total_doc.count"},
                            ]
                        }
                    }
                },
            ]
        )

        q = op.query(
            keywords=keywords,
            synthesis_type=[SynthesisTypeEnum.solid_state],
            target_formula="SiO2",
            precursor_formula="SiO2",
            operations=[OperationTypeEnum.shaping],
            condition_heating_time_min=0,
            condition_heating_time_max=5,
            condition_heating_temperature_min=0,
            condition_heating_temperature_max=5,
            condition_heating_atmosphere=["air"],
            condition_mixing_device=["zirconia"],
            condition_mixing_media=["water"],
            _skip=0,
            _limit=10,
        )

        assert q["pipeline"] == pipeline

        with ScratchDir("."):
            dumpfn(op, "temp.json")
            new_op = loadfn("temp.json")
            q = new_op.query(
                keywords=keywords,
                synthesis_type=[SynthesisTypeEnum.solid_state],
                target_formula="SiO2",
                precursor_formula="SiO2",
                operations=[OperationTypeEnum.shaping],
                condition_heating_time_min=0,
                condition_heating_time_max=5,
                condition_heating_temperature_min=0,
                condition_heating_temperature_max=5,
                condition_heating_atmosphere=["air"],
                condition_mixing_device=["zirconia"],
                condition_mixing_media=["water"],
                _skip=0,
                _limit=10,
            )
            assert q == {"pipeline": pipeline}
