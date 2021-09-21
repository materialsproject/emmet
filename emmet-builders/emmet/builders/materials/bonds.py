from maggma.builders.map_builder import MapBuilder
from maggma.core import Store
from pymatgen.core import Structure
from pymatgen.core import __version__ as pymatgen_version

from emmet.core.bonds import BondingDoc
from emmet.core.utils import jsanitize


class BondingBuilder(MapBuilder):
    def __init__(
        self, oxidation_states: Store, bonding: Store, **kwargs,
    ):
        """
        Creates Bonding documents from structures, ideally with
        oxidation states already annotated but will also work from any
        collection with structure and mp-id.

        Args:
            oxidation_states: Store of oxidation
            bonding: Store to update with bonding documents
            query : query on materials to limit search
        """
        self.oxidation_states = oxidation_states
        self.bonding = bonding
        self.kwargs = kwargs

        # Enforce that we key on material_id
        self.oxidation_states.key = "material_id"
        self.bonding.key = "material_id"
        super().__init__(
            source=oxidation_states,
            target=bonding,
            projection=["structure", "deprecated"],
            **kwargs,
        )

    def unary_function(self, item):
        structure = Structure.from_dict(item["structure"])
        mpid = item["material_id"]
        deprecated = item["deprecated"]

        bonding_doc = BondingDoc.from_structure(
            structure=structure, material_id=mpid, deprecated=deprecated
        )
        doc = jsanitize(bonding_doc.dict(), allow_bson=True)

        return doc
