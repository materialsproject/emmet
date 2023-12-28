from maggma.api.resource import ReadOnlyResource
from emmet.core.molecules.electric import ElectricMultipoleDoc

from maggma.api.query_operator import PaginationQuery, SparseFieldsQuery

from emmet.api.routes.molecules.electric.query_operators import (
    MultipoleMomentComponentQuery,
)
from emmet.api.routes.molecules.molecules.query_operators import (
    MultiMPculeIDQuery,
    ExactCalcMethodQuery,
    FormulaQuery,
    ChemsysQuery,
    ElementsQuery,
    ChargeSpinQuery,
)
from emmet.api.routes.molecules.utils import MethodQuery, MultiPropertyIDQuery
from emmet.api.core.settings import MAPISettings
from emmet.api.core.global_header import GlobalHeaderProcessor


def electric_multipole_resource(multipole_store):
    resource = ReadOnlyResource(
        multipole_store,
        ElectricMultipoleDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            ExactCalcMethodQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            MethodQuery(),
            MultiPropertyIDQuery(),
            MultipoleMomentComponentQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                ElectricMultipoleDoc,
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
        tags=["Molecules Electric Dipoles and Multipoles"],
        sub_path="/multipoles/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
