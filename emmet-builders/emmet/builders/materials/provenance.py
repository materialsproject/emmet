"""Build provenance collection."""

from functools import partial

from emmet.builders.base import BaseBuilderInput
from emmet.builders.settings import EmmetBuildSettings
from emmet.core.connectors.analysis import parse_cif
from emmet.core.connectors.icsd.client import IcsdClient
from emmet.core.connectors.icsd.enums import IcsdSubset
from emmet.core.provenance import DatabaseSNL, ProvenanceDoc

from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

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
            remarks=remarks,
            **kwargs,
        )
    except Exception:
        return None

    if snl and snl.remarks is None:
        return snl
    return None


def update_experimental_icsd_structures():
    """Update the collection of ICSD SNLs."""
    data = []
    with IcsdClient(use_document_model=False) as client:
        for icsd_subset in (
            IcsdSubset.EXPERIMENTAL_METALORGANIC,
            IcsdSubset.EXPERIMENTAL_INORGANIC,
        ):
            data += client.search(
                subset=IcsdSubset.EXPERIMENTAL_INORGANIC,
                space_group_number=(1, 230),
                include_cif=True,
                include_metadata=False,
            )

    parsed = [
        _get_snl_from_cif(
            doc["cif"],
            snl_id=f"icsd-{doc['collection_code']}",
            tags=doc["subset"].value,
            source="icsd",
        )
        for doc in data
    ]

    return sorted(
        [doc for doc in parsed if doc],
        key=lambda doc: int(doc.snl_id.split("-", 1)[-1]),
    )


def match_against_snls(
    input_doc: BaseBuilderInput,
    snls: list[DatabaseSNL],
):
    """Match a single document against the SNL collection."""
    database_ids = {}
    authors = [SETTINGS.DEFAULT_AUTHOR]
    history = [SETTINGS.DEFAULT_HISTORY]
    references = SETTINGS.DEFAULT_REFERENCE
    theoretical = True

    for snl in [
        doc
        for doc in snls
        if doc.chemsys
        == (
            "-".join(sorted(input_doc.structure.composition.chemical_system.split("-")))
        )
    ]:
        if structure_matcher.fit(input_doc.structure, snl.structure):

            if snl.source and snl.source in {"icsd", "pauling"}:
                theoretical = False
                database_ids[snl.source].append(snl.snl_id)

            if snl.about:
                authors.extend(snl.about.authors or [])
                history.extend(snl.about.history or [])

    return ProvenanceDoc.from_structure(
        meta_structure=input_doc.structure,
        material_id=input_doc.material_id,
        database_IDs=database_ids,
        theoretical=theoretical,
        authors=authors,
        history=history,
        references=references,
    )


def build_provenance_docs(
    input_documents: list[BaseBuilderInput],
    snls: list[DatabaseSNL],
) -> list[ProvenanceDoc]:
    """Build the provenance collection."""

    wrapped = partial(match_against_snls, snls=snls)

    return map(wrapped, input_documents)
