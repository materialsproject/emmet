from maggma.builders.map_builder import MapBuilder
from maggma.core import Store
from pymatgen.core import Structure
from pymatgen.core import __version__ as pymatgen_version

from emmet.core.oxidation_states import OxidationStateDoc
from emmet.core.utils import jsanitize


class OxidationStatesBuilder(MapBuilder):
    def __init__(
        self,
        materials: Store,
        oxidation_states: Store,
        query=None,
        **kwargs,
    ):
        """
        Creates Oxidation State documents from materials

        Args:
            materials: Store of materials docs
            oxidation_states: Store to update with oxidation state document
            query : query on materials to limit search
        """
        self.materials = materials
        self.oxidation_states = oxidation_states
        self.kwargs = kwargs
        self.query = query or {}

        # Enforce that we key on material_id
        self.materials.key = "material_id"
        self.oxidation_states.key = "material_id"
        super().__init__(
            source=materials,
            target=oxidation_states,
            projection=["structure", "deprecated"],
            query=query,
            **kwargs,
        )

    def unary_function(self, item):
        structure = Structure.from_dict(item["structure"])
        mpid = item["material_id"]
        deprecated = item["deprecated"]

        oxi_doc = OxidationStateDoc.from_structure(
            structure=structure, material_id=mpid, deprecated=deprecated
        )
        doc = jsanitize(oxi_doc.dict(), allow_bson=True)

        return doc
