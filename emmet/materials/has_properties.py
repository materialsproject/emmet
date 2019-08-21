from collections import namedtuple, defaultdict
from datetime import datetime

from maggma.builders import Builder
from pymongo import UpdateOne

IDGetter = namedtuple("IDGetter", ["filter", "idfield"])
getters = {
    "elasticity": IDGetter({"elasticity": {"$exists": True}}, "task_id"),
    "piezo": IDGetter({"piezo.e_ij_max": {"$exists": True}}, "task_id"),
    "diel": IDGetter({"dielectric.n": {"$exists": True}}, "task_id"),
    "phonons": IDGetter({}, "mp-id"),
    "eos": IDGetter({}, "mp_id"),
    "xas": IDGetter({"valid": True}, "mp_id"),
    "bandstructure": IDGetter({"bs_plot_small": {"$exists": True}}, "task_id"),
    "surfaces": IDGetter({}, "material_id"),
}


class HasProps(Builder):
    def __init__(self, materials, prop_stores, hasprops, **kwargs):
        self.materials = materials
        self.prop_stores = prop_stores
        self.hasprops = hasprops
        self.kwargs = kwargs

        sources = [self.materials] + [
            store for name, store in prop_stores.items() if name in getters
        ]

        super().__init__(sources=sources, targets=[self.hasprops], **kwargs)

    def get_items(self):
        self.ensure_indexes()

        # Get mapping from task_ids
        task_map = self.materials.query({}, [self.materials.key, "task_ids"])
        task_map = {
            t_id: d[self.materials.key] for d in task_map for t_id in d["task_ids"]
        }

        # Get list of properties for has list from various stores
        hasmap = defaultdict(set)
        for prop, getter in getters.items():
            if prop in self.prop_stores:
                self.logger.info(f"Getting updated material IDs for: {prop}")
                store = self.prop_stores[prop]
                mids_to_update = [task_map[tid] for tid in store.distinct(getter.idfield, getter.filter) if tid in task_map]
                for mid in mids_to_update:
                    hasmap[mid].add(prop)

        all_mids = self.materials.distinct(self.materials.key)
        for mid in all_mids:
            if mid not in hasmap:
                hasmap[mid] = {}

        docs = [
            {self.hasprops.key: mid, "has": list(has)} for mid, has in hasmap.items()
        ]

        return docs

    def update_targets(self, items):
        now = datetime.utcnow()
        for item in items:
            item[self.hasprops.lu_field] = now

        if items:
            self.logger.debug(f"Updating {len(items)} items")
            self.hasprops.update(items)
        else:
            self.logger.debug("No items to update")

    def ensure_indexes(self):
        self.materials.ensure_index("has")
        self.materials.ensure_index(self.materials.key)
        self.hasprops.ensure_index(self.hasprops.key)
