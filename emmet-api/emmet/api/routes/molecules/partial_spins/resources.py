from __future__ import annotations

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.molecules.molecules.query_operators import (
    ChargeSpinQuery,
    ChemsysQuery,
    ElementsQuery,
    ExactCalcMethodQuery,
    FormulaQuery,
    MultiMPculeIDQuery,
)
from emmet.api.routes.molecules.utils import MethodQuery, MultiPropertyIDQuery
from emmet.core.molecules.atomic import PartialSpinsDoc
from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource


def spins_resource(spins_store):
    resource = ReadOnlyResource(
        spins_store,
        PartialSpinsDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            ExactCalcMethodQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            MethodQuery(),
            MultiPropertyIDQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                PartialSpinsDoc,
                default_fields=[
                    "molecule_id",
                    "property_id",
                    "solvent",
                    "method",
                    "last_updated",
                ],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Molecules Partial Spins"],
        sub_path="/partial_spins/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
