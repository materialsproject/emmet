from __future__ import annotations

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.molecules.bonds.query_operators import BondTypeLengthQuery
from emmet.api.routes.molecules.molecules.query_operators import (
    ChargeSpinQuery,
    ChemsysQuery,
    ElementsQuery,
    ExactCalcMethodQuery,
    FormulaQuery,
    MultiMPculeIDQuery,
)
from emmet.api.routes.molecules.utils import MethodQuery, MultiPropertyIDQuery
from emmet.core.molecules.bonds import MoleculeBondingDoc
from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource


def bonding_resource(bonds_store):
    resource = ReadOnlyResource(
        bonds_store,
        MoleculeBondingDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            ExactCalcMethodQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            MethodQuery(),
            MultiPropertyIDQuery(),
            BondTypeLengthQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                MoleculeBondingDoc,
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
        tags=["Molecules Bonds"],
        sub_path="/bonding/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
