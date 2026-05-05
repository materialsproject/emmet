from collections import defaultdict
from dataclasses import dataclass

from fastapi import Query
from pymatgen.analysis.magnetism import Ordering

from emmet.api.query_operator import BoolQuery, QueryOperator
from emmet.api.query_operator.core import MultiMaterialIDQuery
from emmet.api.utils import STORE_PARAMS


class HasPropsQuery(QueryOperator):
    """
    Method to generate a query on whether a material has a certain property
    """

    def query(
        self,
        has_props: str | None = Query(
            None,
            description="Comma-delimited list of possible properties given by HasPropsEnum to search for.",
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if has_props:
            for entry in [prop.strip() for prop in has_props.split(",")]:
                crit[f"has_props.{entry}"] = True

        return {"criteria": crit}


@dataclass
class MaterialIDsSearchQuery(MultiMaterialIDQuery):
    """
    Method to generate a query on search docs using multiple material_id values
    """

    def post_process(self, docs, query):
        if not query.get("sort", None):
            mpid_list = (
                query.get("criteria", {}).get("material_id", {}).get("$in", None)
            )

            if mpid_list is not None and "material_id" in query.get("properties", []):
                mpid_mapping = {mpid: ind for ind, mpid in enumerate(mpid_list)}

                docs = sorted(docs, key=lambda d: mpid_mapping[d["material_id"]])

        return docs


@dataclass
class SearchIsStableQuery(BoolQuery):
    """
    Method to generate a query on whether a material is stable
    """

    field_name: str = "is_stable"

    def query(
        self,
        is_stable: bool | None = Query(
            None, description="Whether the material is stable."
        ),
    ):
        return self._prepare_query(is_stable)


class SearchMagneticQuery(QueryOperator):
    """
    Method to generate a query for magnetic data in search docs.
    """

    def query(
        self,
        ordering: Ordering | None = Query(
            None, description="Magnetic ordering of the material."
        ),
    ) -> STORE_PARAMS:
        crit = defaultdict(dict)  # type: dict

        if ordering:
            crit["ordering"] = ordering.value

        return {"criteria": crit}


@dataclass
class SearchIsTheoreticalQuery(BoolQuery):
    """
    Method to generate a query on whether a material is theoretical
    """

    field_name: str = "theoretical"

    def query(
        self,
        theoretical: bool | None = Query(
            None, description="Whether the material is theoretical."
        ),
    ):
        return self._prepare_query(theoretical)


class SearchESQuery(QueryOperator):
    """
    Method to generate a query on search electronic structure data.
    """

    def query(
        self,
        is_gap_direct: bool | None = Query(
            None, description="Whether a band gap is direct or not."
        ),
        is_metal: bool | None = Query(
            None, description="Whether the material is considered a metal."
        ),
    ) -> STORE_PARAMS:
        crit = defaultdict(dict)  # type: dict

        if is_gap_direct is not None:
            crit["is_gap_direct"] = is_gap_direct

        if is_metal is not None:
            crit["is_metal"] = is_metal

        return {"criteria": crit}
