from pydantic import BaseModel

from emmet.builders.utils import filter_map
from emmet.core.summary import (
    AbsorptionData,
    BandstructureSummary,
    ChargeDensityData,
    ChemenvData,
    DielectricSummary,
    DosSummary,
    ElasticitySummary,
    ElectrodesData,
    ElectronicStructureSummary,
    EosData,
    GBSummary,
    MagnetismSummary,
    MaterialsSummary,
    OxiStatesSummary,
    PhononData,
    PiezoelectricSummary,
    ProvenanceSummary,
    SubstratesData,
    SummaryDoc,
    SurfacesSummary,
    ThermoSummary,
    XASSummary,
)


class SummaryBuilderInputs(BaseModel):
    """
    Input model for building summary documents.

    Bundles the property summary documents and property shim documents
    needed to construct a single SummaryDoc. Property summary documents
    contribute field values to the resulting SummaryDoc, while property
    shim documents are used solely to populate the has_props mapping.
    """

    property_summary_docs: list[
        MaterialsSummary
        | ThermoSummary
        | XASSummary
        | GBSummary
        | ElectronicStructureSummary
        | BandstructureSummary
        | DosSummary
        | MagnetismSummary
        | ElasticitySummary
        | DielectricSummary
        | PiezoelectricSummary
        | SurfacesSummary
        | OxiStatesSummary
        | ProvenanceSummary
    ]
    property_shim_docs: list[
        ChargeDensityData
        | EosData
        | PhononData
        | AbsorptionData
        | ElectrodesData
        | SubstratesData
        | ChemenvData
    ]


def build_summary_docs(
    input_documents: list[SummaryBuilderInputs], **kwargs
) -> list[SummaryDoc]:
    """
    Generate summary documents from input property documents.

    Transforms a list of SummaryBuilderInputs into corresponding
    SummaryDoc instances by merging property summary documents and
    property shim documents for each material. Each SummaryDoc
    aggregates fields from all provided property summaries and tracks
    which properties are available via the has_props mapping.

    Caller is responsible for creating SummaryBuilderInputs instances
    within their data pipeline context.

    Args:
        input_documents: List of SummaryBuilderInputs documents to process.

    Returns:
        list[SummaryDoc]
    """
    return filter_map(
        SummaryDoc.from_docs,
        input_documents,
        work_keys=["property_summary_docs", "property_shim_docs"],
        **kwargs
    )
