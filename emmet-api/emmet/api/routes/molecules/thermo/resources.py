from maggma.api.resource import ReadOnlyResource
from emmet.core.molecules.thermo import MoleculeThermoDoc

from maggma.api.query_operator import (
    NumericQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)

from emmet.api.routes.molecules.thermo.query_operators import (
    ThermoCorrectionQuery,
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


def thermo_resource(thermo_store):
    resource = ReadOnlyResource(
        thermo_store,
        MoleculeThermoDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            ExactCalcMethodQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            MultiPropertyIDQuery(),
            ThermoCorrectionQuery(),
            NumericQuery(
                model=MoleculeThermoDoc,
                excluded_fields=[
                    "charge",
                    "spin_multiplicity",
                    "natoms",
                    "nelements",
                    "nelectrons",
                    "rt",
                ],
            ),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(
                MoleculeThermoDoc,
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
        tags=["Molecules Thermo"],
        sub_path="/thermo/",
        disable_validation=True,
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
