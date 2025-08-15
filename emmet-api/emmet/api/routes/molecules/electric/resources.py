from emmet.api.resource import ReadOnlyResource
from emmet.core.molecules.electric import ElectricMultipoleDoc

from emmet.api.query_operator import (
    PaginationQuery,
    SparseFieldsQuery,
    NumericQuery,
)

from emmet.api.routes.molecules.electric.query_operators import (
    MultipoleMomentComponentQuery,
)
from emmet.api.routes.molecules.molecules.query_operators import (
    MultiMPculeIDQuery,
    ExactCalcMethodQuery,
    FormulaQuery,
    ChemsysQuery,
    CompositionElementsQuery,
    ChargeSpinQuery,
)
from emmet.api.routes.molecules.utils import MultiPropertyIDQuery
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
            CompositionElementsQuery(),
            ChargeSpinQuery(),
            MultiPropertyIDQuery(),
            MultipoleMomentComponentQuery(),
            PaginationQuery(),
            NumericQuery(
                model=ElectricMultipoleDoc,
                fields=[
                    "total_dipole",
                    "resp_total_dipole",
                ],
            ),
            SparseFieldsQuery(
                ElectricMultipoleDoc,
                default_fields=[
                    "molecule_id",
                    "property_id",
                    "solvent",
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
