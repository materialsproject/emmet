from maggma.api.resource import AggregationResource

from emmet.api.routes.synthesis.query_operators import SynthesisSearchQuery
from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.core.synthesis.core import SynthesisSearchResultModel

synth_indexes = [
    ("synthesis_type", False),
    ("targets_formula_s", False),
    ("precursors_formula_s", False),
    ("operations.type", False),
    ("operations.conditions.heating_temperature.values", False),
    ("operations.conditions.heating_time.values", False),
    ("operations.conditions.heating_atmosphere", False),
    ("operations.conditions.mixing_device", False),
    ("operations.conditions.mixing_media", False),
]


def synth_resource(synth_store):

    resource = AggregationResource(
        synth_store,
        SynthesisSearchResultModel,
        tags=["Synthesis"],
        pipeline_query_operator=SynthesisSearchQuery(),
        header_processor=GlobalHeaderProcessor(),
    )

    return resource
