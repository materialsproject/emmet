from maggma.api.resource import ReadOnlyResource
from emmet.core.molecules.orbitals import OrbitalDoc

from maggma.api.query_operator import PaginationQuery, SortQuery, SparseFieldsQuery

from emmet.api.routes.molecules.orbitals.query_operators import (
    NBOPopulationQuery,
    NBOLonePairQuery,
    NBOBondQuery,
    NBOInteractionQuery,
)
from emmet.api.routes.molecules.molecules.query_operators import (
    MultiMPculeIDQuery,
    ExactCalcMethodQuery,
    FormulaQuery,
    ChemsysQuery,
    ElementsQuery,
    ChargeSpinQuery,
)
from emmet.api.routes.molecules.utils import MultiPropertyIDQuery
from emmet.api.core.settings import MAPISettings
from emmet.api.core.global_header import GlobalHeaderProcessor


def orbitals_resource(orbital_store):
    resource = ReadOnlyResource(
        orbital_store,
        OrbitalDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            ExactCalcMethodQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            MultiPropertyIDQuery(),
            NBOPopulationQuery(),
            NBOLonePairQuery(),
            NBOBondQuery(),
            NBOInteractionQuery(),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                OrbitalDoc,
                default_fields=[
                    "molecule_id",
                    "property_id",
                    "solvent",
                    "last_updated",
                ],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Molecules Orbitals"],
        sub_path="/orbitals/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
