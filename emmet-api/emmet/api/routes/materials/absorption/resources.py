from __future__ import annotations

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.materials.materials.query_operators import MultiMaterialIDQuery
from emmet.core.absorption import AbsorptionDoc
from maggma.api.query_operator import (
    NumericQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from maggma.api.resource import ReadOnlyResource


def absorption_resource(absorption_store):
    resource = ReadOnlyResource(
        absorption_store,
        AbsorptionDoc,
        query_operators=[
            MultiMaterialIDQuery(),
            NumericQuery(
                model=AbsorptionDoc,
                excluded_fields=[
                    "energies",
                    "absorption_coefficient",
                    "average_imaginary_dielectric",
                    "average_real_dielectric",
                    "nkpoints",
                    "energy_max",
                ],
            ),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                AbsorptionDoc,
                default_fields=["material_id", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Materials Absorption"],
        sub_path="/absorption/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
