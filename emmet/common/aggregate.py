from datetime import datetime

from maggma.builder import Builder
from maggma.utils import recursive_update

class AggregateBuilder(Builder):
    """
    Concats multiple collections together

    Uses `lu_field` to get new/updated documents,
    and uses a `key` field to determine which documents to merge together

    """

    def __init__(self, sources, target, key_field, **kwargs):
        self.key_field = key_field
        self.sources = sources
        self.target = target
        self.kwargs = kwargs

        super(AggregateBuilder, self).__init__(sources=sources, targets=[target], **kwargs)

    def get_items(self):

        keys_to_update = set()

        for source in self.sources:
            keys_to_update |= set(source().distinct(self.key_field,source.lu_filter(self.targets)))

        for key in keys_to_update:
            d = {}
            for source in self.sources:
                recursive_update(d,source().find_one({self.key_field: key}))
                d.pop(source.lu_field)
            yield d

    def update_targets(self, items):

        bulk = self.target().initialize_ordered_bulk_op()
        for item in items:
            item.pop("_id",None)  # Don't alter immutable field in target.
            item[self.target.lu_field] = datetime.utcnow()
            # Use source last-updated value, ensuring `datetime` type.
            bulk.find({self.key_field:item[self.key_field]}).upsert().replace_one(item)
        bulk.execute()
