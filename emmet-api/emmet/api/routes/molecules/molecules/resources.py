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


def find_molecule_resource(molecules_store):
    resource = PostOnlyResource(
        molecules_store,
        FindMolecule,
        key_fields=["molecule", "molecule_id"],
        query_operators=[FindMoleculeQuery()],
        tags=["Core Molecules"],
        sub_path="/core/find_molecule/",
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
            SparseFieldsQuery(
                MoleculeDoc,
                default_fields=["molecule_id", "formula_alphabetical", "last_updated"],
            ),
        ],
        header_processor=GlobalHeaderProcessor(),
        tags=["Core Molecules"],
        sub_path="/core/",
        disable_validation=True,
        hint_scheme=MoleculesHintScheme(),
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
