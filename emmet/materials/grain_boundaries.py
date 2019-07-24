from datetime import datetime
from enum import Enum

from bson import ObjectId
from maggma.builders import MapBuilder, Builder
from pymatgen import Structure
from pydantic import BaseModel, constr, conlist
from atomate.utils.utils import get_meta_from_structure


def processed(doc):
    out = doc.copy()
    structure = Structure.from_dict(doc["final_structure"])
    out["cif"] = structure.to(fmt="cif")
    meta = get_meta_from_structure(structure)
    out.update(pretty_formula=meta["formula_pretty"], chemsys=meta["chemsys"])
    out["type"] = "twist" if doc["rotation_axis"] == doc["gb_plane"] else "tilt"
    Target(**out)  # raises pydantic.ValidationError if violates schema
    return out


class GBType(str, Enum):
    tilt = "tilt"
    twist = "twist"


class Target(BaseModel):
    material_id: constr(regex=r"(?:mp|mvc)\-\d+")
    gb_energy: float
    sigma: int
    rotation_axis: conlist(int, min_items=3, max_items=4)
    rotation_angle: float
    gb_plane: conlist(int, min_items=3, max_items=4)
    chemsys: str
    pretty_formula: str
    initial_structure: dict
    final_structure: dict
    task_id: int
    _id: ObjectId
    cif: str
    type: GBType


class WorkOfSeparation(Builder):
    def __init__(self, surface_properties, grain_boundaries, gbs_with_wsep):
        self.surface_properties = surface_properties
        self.grain_boundaries = grain_boundaries
        self.gbs_with_wsep = gbs_with_wsep
        super().__init__(
            sources=[surface_properties, grain_boundaries],
            targets=[gbs_with_wsep])

    def get_items(self):
        self.logger.info("Starting {} Builder".format(self.__class__.__name__))
        gbs = {
            doc[self.grain_boundaries.key]: doc
            for doc in self.grain_boundaries.query()
        }
        surfaces = {
            doc["material_id"]: doc["surfaces"]
            for doc in self.surface_properties.query({}, ["material_id", "surfaces"])
        }
        self.logger.info("Processing {} items".format(len(gbs)))
        for gb in list(gbs.values()):
            try:
                gb["material_surfaces"] = surfaces[gb["material_id"]]
            except KeyError:
                self.logger.debug(f'No surface properties for {gb["material_id"]}')
        return list(gbs.values())

    def process_item(self, item):
        for surf in item.get("material_surfaces", []):
            if surf["miller_index"] == item['gb_plane']:
                item["w_sep"] = 2 * surf['surface_energy'] - item['gb_energy']  # work of separation
                break
        item.pop("material_surfaces", None)
        return item

    def update_targets(self, items):
        source, target = self.grain_boundaries, self.gbs_with_wsep
        for item in items:
            # Use source last-updated value, ensuring `datetime` type.
            source_lu = source.lu_func[0](item[source.lu_field])
            item[target.lu_field] = source_lu
            if source.lu_field != target.lu_field:
                del item[source.lu_field]
            item["_bt"] = datetime.utcnow()
            if "_id" in item:
                del item["_id"]

        if len(items) > 0:
            target.update(items, update_lu=False)


class GrainBoundaries(MapBuilder):
    def __init__(self, source, target, **kwargs):
        super().__init__(source=source, target=target, ufn=processed, store_process_time=False, **kwargs)

    def ensure_indexes(self):
        super().ensure_indexes()
        search_keys = ("material_id", "gb_plane", "sigma", "chemsys", "pretty_formula")
        for k in search_keys:
            self.target.ensure_index(k)
