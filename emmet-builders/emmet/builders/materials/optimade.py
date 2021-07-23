from maggma.builders.map_builder import MapBuilder
from maggma.core import Store
from pymatgen.core.structure import Structure

from emmet.core.optimade import OptimadeMaterialsDoc
from emmet.core.utils import jsanitize


class OptimadeMaterialsBuilder(MapBuilder):
    def __init__(
        self,
        materials: Store,
        optimade: Store,
        **kwargs,
    ):
        """
        Creates Optimade compatible structure docs for the materials

        Args:
            materials: Store of materials docs
            optimade: Store to update with optimade document
            query : query on materials to limit search
        """
        self.materials = materials
        self.optimade = optimade
        self.kwargs = kwargs

        # Enforce that we key on material_id
        self.materials.key = "material_id"
        self.optimade.key = "material_id"
        super().__init__(
            source=materials,
            target=optimade,
            projection=["structure"],
            **kwargs,
        )

    def unary_function(self, item):
        structure = Structure.from_dict(item["structure"])
        mpid = item["material_id"]
        last_updated = item["last_updated"]

        optimade_doc = OptimadeMaterialsDoc.from_structure(
            structure=structure, material_id=mpid, last_updated=last_updated
        )
        doc = jsanitize(optimade_doc.dict(), allow_bson=True)

        return doc
