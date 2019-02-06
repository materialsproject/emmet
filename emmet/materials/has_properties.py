from collections import namedtuple, defaultdict

from maggma.builders import Builder
from pymongo import UpdateOne

IDGetter = namedtuple("IDGetter", ["filter", "idfield"])
getters = {
    "elasticity": IDGetter({"elasticity": {"$exists": True}}, "task_id"),
    "piezo": IDGetter({"piezo": {"$exists": True}}, "task_id"),
    "diel": IDGetter({"diel": {"$exists": True}}, "task_id"),
    "phonons": IDGetter({}, "mp-id"),
    "eos": IDGetter({}, "mp_id"),
    "xas": IDGetter({"valid": True}, "mp_id"),
    "bandstructure": IDGetter({"has_bandstructure": True}, "task_id"),
    "surfaces": IDGetter({}, "material_id"),
}


class HasProps(Builder):
    def __init__(self, materials, prop_stores, hasprops, **kwargs):
        self.materials = materials
        sources = [self.materials]
        for key in (set(prop_stores) - set(getters)):
            del prop_stores[key]
        self.prop_stores = prop_stores
        sources.extend(list(self.prop_stores.values()))
        self.hasprops = hasprops
        self.kwargs = kwargs
        super().__init__(sources=sources, targets=[self.hasprops], **kwargs)

    def get_items(self):
        self.materials.ensure_index("has")
        self.hasprops.ensure_index("task_id")
        hasmap = defaultdict(set)
        for prop, getter in getters.items():
            self.logger.info(f"{prop}: getting mids to update...")
            store = self.prop_stores[prop]
            mids_to_update = store.distinct(getter.idfield, getter.filter)
            if store.collection.full_name != self.materials.collection.full_name:
                # Resolve to canonical mids
                mids_to_update = self.materials.distinct("task_id", {"task_ids": {"$in": mids_to_update}})
            for mid in mids_to_update:
                hasmap[mid].add(prop)
        upstream = {d["task_id"]: set(d["has"]) for d in self.hasprops.query({}, ["task_id", "has"])}
        todo = [({"task_id": mid}, {"$set": {"has": list(props)}})
                for mid, props in hasmap.items() if props != upstream.get(mid)]
        return todo

    def update_targets(self, items):
        requests = [UpdateOne(*item, upsert=True) for item in items]
        self.hasprops.collection.bulk_write(requests, ordered=False)
