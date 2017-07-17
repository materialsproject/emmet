from datetime import datetime

from maggma.builder import Builder
from pydash import py_
from tqdm import tqdm


class CopyBuilder(Builder):
    """Sync a source with a target.

    Uses `lu_field` of source and target Store to get new/updated documents,
    and uses a `key` function to filter for the target document to update.

    """

    def __init__(self, *args, key=lambda d: {'_id': d['_id']}, **kwargs):
        super(CopyBuilder, self).__init__(*args, **kwargs)
        assert len(self.sources) == 1 and len(self.targets) == 1
        self.key = key

    def get_items(self):
        source = self.sources[0]
        cursor = source.collection.find(
            source.lu_filter(self.targets), sort=[(source.lu_field, 1)])
        return tqdm(cursor, total=cursor.count())

    def process_item(self, item):
        return item

    def update_targets(self, items):
        source, target = self.sources[0], self.targets[0]
        bulk = target.collection.initialize_ordered_bulk_op()
        for item in items:
            del item['_id']  # Don't alter immutable field in target.
            # Use source last-updated value, ensuring `datetime` type.
            item[target.lu_field] = source.lu_key[0](item[source.lu_field])
            del item[source.lu_field]
            bulk.find(self.key(item)).upsert().replace_one(item)
        bulk.execute()
