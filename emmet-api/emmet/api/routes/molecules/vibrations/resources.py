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
from emmet.api.routes.molecules.utils import MultiPropertyIDQuery
from emmet.core.molecules.vibration import VibrationDoc
from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery
from maggma.api.resource import ReadOnlyResource


def vibration_resource(vibes_store):
    resource = ReadOnlyResource(
        vibes_store,
        VibrationDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            ExactCalcMethodQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            MultiPropertyIDQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                VibrationDoc,
                default_fields=[
                    "molecule_id",
                    "property_id",
                    "solvent",
                    "last_updated",
                ],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Molecules Vibrations"],
        sub_path="/vibrations/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
