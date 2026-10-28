from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import IdFormatQuery
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
        # Accepted for consistency across endpoints: no MP identifiers are
        # returned, so nothing is converted (yet)
        query_operators=[IdFormatQuery(model=SynthesisSearchResultModel)],
        header_processor=GlobalHeaderProcessor(),
        timeout=MAPISettings().TIMEOUT,
    )

    return resource
