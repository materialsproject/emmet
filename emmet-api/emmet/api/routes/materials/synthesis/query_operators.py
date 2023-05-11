from typing import Optional, List, Dict, Union, Any
from fastapi import Query
from pymatgen.core import Composition
from maggma.api.query_operator import QueryOperator
from emmet.core.synthesis import SynthesisTypeEnum, OperationTypeEnum
from emmet.api.routes.materials.synthesis.utils import mask_highlights, mask_paragraphs


class SynthesisSearchQuery(QueryOperator):
    """
    Method to generate a synthesis text search query
    """

    def query(  # noqa: C901
        self,
        keywords: Optional[str] = Query(
            None,
            description="Comma delimited string keywords to search synthesis paragraph text with.",
        ),
        synthesis_type: Optional[List[SynthesisTypeEnum]] = Query(
            None, description="Type of synthesis to include."
        ),
        target_formula: Optional[str] = Query(
            None, description="Chemical formula of the target material."
        ),
        precursor_formula: Optional[str] = Query(
            None, description="Chemical formula of the precursor material."
        ),
        operations: Optional[List[OperationTypeEnum]] = Query(
            None, description="List of operations that syntheses must have."
        ),
        condition_heating_temperature_min: Optional[float] = Query(
            None, description="Minimal heating temperature."
        ),
        condition_heating_temperature_max: Optional[float] = Query(
            None, description="Maximal heating temperature."
        ),
        condition_heating_time_min: Optional[float] = Query(
            None, description="Minimal heating time."
        ),
        condition_heating_time_max: Optional[float] = Query(
            None, description="Maximal heating time."
        ),
        condition_heating_atmosphere: Optional[List[str]] = Query(
            None, description='Required heating atmosphere, such as "air", "argon".'
        ),
        condition_mixing_device: Optional[List[str]] = Query(
            None, description='Required mixing device, such as "zirconia", "Al2O3".'
        ),
        condition_mixing_media: Optional[List[str]] = Query(
            None, description='Required mixing media, such as "alcohol", "water".'
        ),
        _skip: int = Query(0, description="Number of entries to skip in the search"),
        _limit: int = Query(
            10,
            description="Max number of entries to return in a single query. Limited to 10.",
        ),
    ):
        project_dict: Dict[str, Union[Dict, int]] = {
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

        pipeline: List[Any] = []

        if keywords:
            pipeline.insert(
                0,
                {
                    "$search": {
                        # NOTICE to MongoDB admin:
                        # This MongoDB Atlas index should be created with:
                        # {"mappings": { "dynamic": false,
                        #   "fields": {
                        #     "paragraph_string": {"type": "string"}
                        #   }}}
                        "index": "synth_descriptions",
                        "search": {
                            "query": [
                                keyword.strip() for keyword in keywords.split(",")
                            ],
                            "path": "paragraph_string",
                        },
                        "highlight": {
                            "path": "paragraph_string",
                            # "maxNumPassages": 1
                        },
                    }
                },
            )
            project_dict.update(
                {
                    "search_score": {"$meta": "searchScore"},
                    "highlights": {"$meta": "searchHighlights"},
                }
            )

        pipeline.append({"$project": project_dict})

        crit: Dict[str, Any] = {}

        if synthesis_type:
            crit["synthesis_type"] = {"$in": synthesis_type}
        if target_formula:
            reduced_formula = Composition(
                target_formula
            ).get_reduced_formula_and_factor()[0]
            crit["targets_formula_s"] = reduced_formula
        if precursor_formula:
            reduced_formula = Composition(
                precursor_formula
            ).get_reduced_formula_and_factor()[0]
            crit["precursors_formula_s"] = reduced_formula
        if operations:
            crit["operations.type"] = {"$all": operations}
        if condition_heating_temperature_min is not None:
            field = "operations.conditions.heating_temperature.values"
            if field not in crit:
                crit[field] = {"$elemMatch": {}}
            crit[field]["$elemMatch"]["$gte"] = condition_heating_temperature_min
        if condition_heating_temperature_max is not None:
            field = "operations.conditions.heating_temperature.values"
            if field not in crit:
                crit[field] = {"$elemMatch": {}}
            crit[field]["$elemMatch"]["$lte"] = condition_heating_temperature_max
        if condition_heating_time_min is not None:
            field = "operations.conditions.heating_time.values"
            if field not in crit:
                crit[field] = {"$elemMatch": {}}
            crit[field]["$elemMatch"]["$gte"] = condition_heating_time_min
        if condition_heating_time_max is not None:
            field = "operations.conditions.heating_time.values"
            if field not in crit:
                crit[field] = {"$elemMatch": {}}
            crit[field]["$elemMatch"]["$lte"] = condition_heating_time_max
        if condition_heating_atmosphere:
            crit["operations.conditions.heating_atmosphere"] = {
                "$all": condition_heating_atmosphere
            }
        if condition_mixing_device:
            crit["operations.conditions.mixing_device"] = {
                "$all": condition_mixing_device
            }
        if condition_mixing_media:
            crit["operations.conditions.mixing_media"] = {
                "$all": condition_mixing_media
            }

        if crit:
            if keywords:
                pipeline.insert(2, {"$match": crit})
            else:
                pipeline.insert(0, {"$match": crit})

        pipeline.append(
            {
                "$facet": {
                    "results": [{"$skip": _skip}, {"$limit": _limit}]
                    if not keywords
                    else [
                        {"$sort": {"search_score": -1}},
                        {"$skip": _skip},
                        {"$limit": _limit},
                    ],
                    "total_doc": [{"$count": "count"}],
                }
            }
        )

        pipeline.extend(
            [
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

        return {"pipeline": pipeline}

    def post_process(self, docs, query):
        self.total_doc = 0

        if len(docs) > 0:
            self.total_doc = docs[0]["total_doc"]

        for doc in docs:
            mask_highlights(doc)
            mask_paragraphs(doc)

        return docs

    def meta(self):
        return {"total_doc": self.total_doc}
