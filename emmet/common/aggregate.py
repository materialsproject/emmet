from datetime import datetime

from maggma.builders import Builder
from maggma.utils import recursive_update

class AggregateBuilder(Builder):
    """
    Concats multiple collections together

    Uses `lu_field` to get new/updated documents,
    and uses a `key` field to determine which documents to merge together

    """

    def __init__(self, sources, target, key_field, aggregate_mode="Update", query = {},**kwargs):
        self.key_field = key_field
        self.sources = sources
        self.aggregate_mode = aggregate_mode
        self.target = target
        self.kwargs = kwargs
        self.query = query

        super(AggregateBuilder, self).__init__(sources=sources, targets=[target], **kwargs)

    def get_items(self):

        keys_to_update = set()

        for source in self.sources:
            new_q = dict(self.query)
            new_q.update(source.lu_filter(self.targets))
            keys_to_update |= set(source().distinct(self.key_field,new_q))

        for key in keys_to_update:
            d = {}
            for source in self.sources:
                doc = source().find_one({self.key_field: key})
                if doc:
                    if self.aggregate_mode is "Overwrite":
                        for k,v in doc.items():
                            d[k] = v
                    else:
                        recursive_update(d, doc)
                    d.pop(source.lu_field)
            yield d

    def update_targets(self, items):

        bulk = self.target().initialize_ordered_bulk_op()
        for item in items:
            # Don't alter immutable field _id in target.
            item.pop("_id",None)
            # set a new updated field
            item[self.target.lu_field] = datetime.utcnow()
            bulk.find({self.key_field:item[self.key_field]}).upsert().replace_one(item)
        bulk.execute()
