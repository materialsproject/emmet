from maggma.api.resource.read_resource import ReadOnlyResource
from maggma.api.resource.post_resource import PostOnlyResource


from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.find_structure import FindMolecule, FindMoleculeConnectivity

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
    FindMoleculeQuery,
    FindMoleculeConnectivityQuery,
    CalcMethodQuery,
    HashQuery
)

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings

timeout = MAPISettings().TIMEOUT


def find_molecule_resource(molecules_store):
    resource = PostOnlyResource(
        molecules_store,
        FindMolecule,
        key_fields=["molecule", "molecule_id"],
        query_operators=[FindMoleculeQuery()],
        tags=["Molecules"],
        sub_path="/find_molecule/",
        timeout=timeout,
    )

    return resource


def find_molecule_connectivity_resource(molecules_store):
    resource = PostOnlyResource(
        molecules_store,
        FindMoleculeConnectivity,
        key_fields=["molecule", "molecule_id"],
        query_operators=[FindMoleculeConnectivityQuery()],
        tags=["Molecules"],
        sub_path="/find_molecule_connectivity/",
        timeout=timeout,
    )

    return resource


def molecules_resource(molecules_store):
    resource = ReadOnlyResource(
        molecules_store,
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
        tags=["Molecules"],
        disable_validation=True,
        hint_scheme=MoleculesHintScheme(),
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
