"""Build provenance collection."""

import logging
from collections import defaultdict
from itertools import chain, groupby
from typing import Iterator

from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher

from emmet.builders.base import BaseBuilderInput
from emmet.builders.settings import EmmetBuildSettings
from emmet.builders.utils import filter_map
from emmet.core.connectors.analysis import parse_cif
from emmet.core.connectors.icsd.client import IcsdClient
from emmet.core.connectors.icsd.enums import IcsdSubset
from emmet.core.provenance import DatabaseSNL, ProvenanceDoc

SETTINGS = EmmetBuildSettings()
structure_matcher = StructureMatcher(
    ltol=SETTINGS.LTOL,
    stol=SETTINGS.STOL,
    comparator=ElementComparator(),
    angle_tol=SETTINGS.ANGLE_TOL,
    primitive_cell=True,
    scale=True,
    attempt_supercell=False,
    allow_subset=False,
)


logger = logging.getLogger(__name__)


def _get_snl_from_cif(cif_str: str, **kwargs) -> DatabaseSNL | None:
    """Build a database SNL from a CIF plus its metadata.

    NB: Only takes the first structure from a CIF.
    While a CIF can technically contain many structures,
    the ICSD usually only distributes CIFs with one structure
    per file.

    Parameters
    -----------
    cif_str : the CIF to parse
    **kwargs to pass to `DatabaseSNL`
    """
    try:
        structures, cif_parsing_remarks = parse_cif(cif_str)
        remarks = kwargs.pop("remarks", None) or cif_parsing_remarks or None
        snl = DatabaseSNL.from_structure(
            meta_structure=structures[0],
            structure=structures[0],
            **kwargs,
        )

        snl.about.remarks = remarks

    except Exception as e:
        logger.warning(e)
        snl = None

    return snl


def update_experimental_icsd_structures(**client_kwargs) -> list[DatabaseSNL]:
    """Update the collection of ICSD SNLs.

    Parameters
    -----------
    **client_kwargs to pass to `IcsdClient`

    Returns
    -----------
    List of DatabaseSNL
    """
    data = []
    with IcsdClient(use_document_model=False, **client_kwargs) as client:
        for icsd_subset in (
            IcsdSubset.EXPERIMENTAL_METALORGANIC,
            IcsdSubset.EXPERIMENTAL_INORGANIC,
        ):
            data += client.search(
                subset=icsd_subset,
                space_group_number=(1, 230),
                include_cif=False,
                include_metadata=False,
            )
    return data

    parsed = [
        _get_snl_from_cif(
            doc["cif"],
            snl_id=f"icsd-{doc['collection_code']}",
            tags=[doc["subset"].value],
            source="icsd",
        )
        for doc in data
    ]

    return sorted(
        [doc for doc in parsed if doc],
        key=lambda doc: int(doc.snl_id.split("-", 1)[-1]),
    )


class ProvenanceBuilderInput(BaseBuilderInput):
    formula_pretty: str


def _match_against_snls(
    inputs: tuple[list[ProvenanceBuilderInput], list[DatabaseSNL]],
) -> list[ProvenanceDoc]:
    """
    Structure match a set of ProvenanceBuilderInputs against a group of DatabaseSNLs

    Should be used in conjunction with ``build_provenance_docs`` to ensure inputs
    are correctly grouped by 'formula_pretty'.
    """
    input_documents, snls = inputs

    results = []
    for input_doc in input_documents:
        authors = [[SETTINGS.DEFAULT_AUTHOR]]
        database_ids = defaultdict(list)
        history = [[SETTINGS.DEFAULT_HISTORY]]
        references = [SETTINGS.DEFAULT_REFERENCE]
        theoretical = True

        if snls:
            for snl in snls:
                if structure_matcher.fit(input_doc.structure, snl.structure):
                    if snl.source and snl.source in {"icsd", "pauling"}:
                        theoretical = False
                        database_ids[snl.source].append(snl.snl_id)

                    if snl.about:
                        authors.append(snl.about.authors or [])
                        history.append(snl.about.history or [])
                        # `SNLAbout` uses string for `references`,
                        # `ProvenanceDoc` uses list of str
                        if snl.about.references:
                            references.append(snl.about.references)

        results.append(
            ProvenanceDoc.from_structure(
                meta_structure=input_doc.structure,
                material_id=input_doc.material_id,
                database_IDs=database_ids,
                theoretical=theoretical,
                authors=list(chain.from_iterable(authors)),
                history=list(chain.from_iterable(history)),
                references=references,
            )
        )

    return results


def build_provenance_docs(
    input_documents: list[ProvenanceBuilderInput], snls: list[DatabaseSNL], **kwargs
) -> Iterator[ProvenanceDoc]:
    """
    Groups input documents and SNLs by formula_pretty, performs structure matching
    on each formula group, and constructs ProvenanceDocs for each group of
    ProvenanceBuilderInputs with matching structures within each formula group.

    Args:
        input_documents: List of ProvenanceBuilderInput objects to process.
        snls: List of DatabaseSNL objects for structure matching against.

    Returns:
        Iterator[ProvenanceDoc]
    """

    input_documents.sort(key=lambda x: x.formula_pretty)
    snls.sort(key=lambda y: y.formula_pretty)

    input_docs = dict()
    for form, input_group in groupby(input_documents, key=lambda x: x.formula_pretty):
        input_docs[form] = list(input_group)

    snl_docs = dict()
    for form, snl_group in groupby(snls, key=lambda y: y.formula_pretty):
        snl_docs[form] = list(snl_group)

    inputs = [(inp, snl_docs.get(form, [])) for form, inp in input_docs.items()]

    return chain.from_iterable(filter_map(_match_against_snls, inputs, **kwargs))
