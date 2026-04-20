from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS
from emmet.core.mpid_ext import SuffixedID


class SuffixedIDQuery(QueryOperator):
    """Query a suffixed identifier field.

    Supports querying one or multiple suffixed IDs.

    Will assume that the name of the input query is
    `field_name`s.

    See emmet.api.routes.materials.thermo.query_operators.MultiThermoIDQuery
    for a concrete implementation.
    """

    suffix_id_class: SuffixedID = SuffixedID
    field_name: str = "identifier"

    def query(
        self,
        **kwargs,
    ) -> STORE_PARAMS:

        identifiers = [v.strip() for v in kwargs.get(f"{self.field_name}s") or ""]
        sfx_ids = [self.suffix_id_class.from_str(v).model_dump() for v in identifiers]

        if len(sfx_ids) == 0:
            # Originally it was supported to query by a null value, quick return if so
            return {}
        elif len(sfx_ids) == 1:
            # If only one ID specified, then just add a match to aggregation
            return {
                "criteria": {
                    f"{self.field_name}.identifier": sfx_ids[0]["identifier"],
                    f"{self.field_name}.suffix": sfx_ids[0]["suffix"],
                    f"{self.field_name}.separator": sfx_ids[0].separator,
                }
            }

        # If multiple IDs specified, perform aggregation

        pre_filter_q = {}

        for field in ("identifier", "suffix"):
            if len(unique := list({idx for idx in sfx_ids})) == 1:
                pre_filter_q[f"{self.field_name}.{field}"] = unique[0]
            else:
                pre_filter_q[f"{self.field_name}.{field}"] = {"$in": unique}

        pipeline = [
            {
                # pre-filter based on specified unique IDs / suffixes
                "$match": pre_filter_q
            },
            {
                # concatenate suffixed ID field
                "$addFields": {
                    "_idcat": {
                        "$concat": [
                            f"${self.field_name}.identifier",
                            f"${self.field_name}.separator",
                            f"${self.field_name}.suffix",
                        ]
                    }
                }
            },
            {
                # match concatenated suffix ID
                "$match": {"_idcat": {"$in": identifiers}}
            },
            {
                # remove from output
                "$unset": "_idcat"
            },
        ]

        return {"pipeline": pipeline}
