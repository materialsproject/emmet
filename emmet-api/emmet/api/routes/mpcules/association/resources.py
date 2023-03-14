from maggma.api.resource.read_resource import ReadOnlyResource


from emmet.core.qchem.molecule import MoleculeDoc

from maggma.api.query_operator import (
    PaginationQuery,
    SparseFieldsQuery,
    SortQuery,
    NumericQuery,
)

from emmet.api.routes.mpcules.molecules.hint_scheme import MoleculesHintScheme
from emmet.api.routes.mpcules.molecules.query_operators import (
    FormulaQuery,
    ChemsysQuery,
    ElementsQuery,
    ChargeSpinQuery,
    DeprecationQuery,
    MultiTaskIDQuery,
    MultiMPculeIDQuery,
    CalcMethodQuery,
    HashQuery
)

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings

timeout = MAPISettings().TIMEOUT


def mol_assoc_resource(assoc_store):
    resource = ReadOnlyResource(
        assoc_store,
        MoleculeDoc,
        query_operators=[
            MultiMPculeIDQuery(),
            FormulaQuery(),
            ChemsysQuery(),
            ElementsQuery(),
            ChargeSpinQuery(),
            MultiTaskIDQuery(),
            CalcMethodQuery(),
            HashQuery(),
            DeprecationQuery(),
            NumericQuery(model=MoleculeDoc),
            SortQuery(),
            PaginationQuery(),
            SparseFieldsQuery(MoleculeDoc, default_fields=["molecule_id", "formula_alphabetical", "last_updated"],),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["MPcules Associated Molecules"],
        sub_path="/assoc/",
        disable_validation=True,
        hint_scheme=MoleculesHintScheme(),
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
