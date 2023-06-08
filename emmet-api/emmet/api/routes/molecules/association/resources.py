from __future__ import annotations

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.routes.molecules.molecules.hint_scheme import MoleculesHintScheme
from emmet.api.routes.molecules.molecules.query_operators import (
    CalcMethodQuery,
    ChargeSpinQuery,
    ChemsysQuery,
    DeprecationQuery,
    ElementsQuery,
    FindMoleculeQuery,
    FormulaQuery,
    HashQuery,
    MultiMPculeIDQuery,
    MultiTaskIDQuery,
)
from emmet.core.find_structure import FindMolecule
from emmet.core.qchem.molecule import MoleculeDoc
from maggma.api.query_operator import (
    NumericQuery,
    PaginationQuery,
    SortQuery,
    SparseFieldsQuery,
)
from maggma.api.resource.post_resource import PostOnlyResource
from maggma.api.resource.read_resource import ReadOnlyResource

timeout = MAPISettings().TIMEOUT


def find_molecule_assoc_resource(assoc_store):
    resource = PostOnlyResource(
        assoc_store,
        FindMolecule,
        key_fields=["molecule", "molecule_id"],
        query_operators=[FindMoleculeQuery()],
        tags=["Associated Molecules"],
        sub_path="/assoc/find_molecule/",
        timeout=timeout,
    )

    return resource


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
            SparseFieldsQuery(
                MoleculeDoc,
                default_fields=["molecule_id", "formula_alphabetical", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Associated Molecules"],
        sub_path="/assoc/",
        disable_validation=True,
        hint_scheme=MoleculesHintScheme(),
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
