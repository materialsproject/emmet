from typing import Dict, Optional
from maggma.builders.map_builder import MapBuilder
from maggma.core import Store

from pymatgen.core.structure import Structure
from emmet.core.robocrys import RobocrystallogapherDoc
from emmet.core.utils import jsanitize


class RobocrystallographerBuilder(MapBuilder):
    def __init__(
        self,
        oxidation_states: Store,
        robocrys: Store,
        query: Optional[Dict] = None,
        **kwargs
    ):
        self.oxidation_states = oxidation_states
        self.robocrys = robocrys
        self.kwargs = kwargs

        self.robocrys.key = "material_id"
        self.oxidation_states.key = "material_id"

        super().__init__(
            source=oxidation_states,
            target=robocrys,
            query=query,
            projection=["material_id", "structure", "deprecated"],
            **kwargs
        )

    def unary_function(self, item):
        structure = Structure.from_dict(item["structure"])
        mpid = item["material_id"]
        deprecated = item["deprecated"]

        doc = RobocrystallogapherDoc.from_structure(
            structure=structure,
            material_id=mpid,
            deprecated=deprecated,
            fields=[],
        )

        return jsanitize(doc.model_dump(), allow_bson=True)
