from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.resource import AggregationResource
from emmet.api.routes.materials.synthesis.query_operators import SynthesisSearchQuery
from emmet.core.synthesis.core import SynthesisSearchResultModel


def synth_resource(synth_store):
    resource = AggregationResource(
        synth_store,
        SynthesisSearchResultModel,
        tags=["Materials Synthesis"],
        sub_path="/synthesis/",
        pipeline_query_operator=SynthesisSearchQuery(),
        header_processor=GlobalHeaderProcessor(),
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
