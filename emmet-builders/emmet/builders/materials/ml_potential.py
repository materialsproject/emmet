from emmet.core.ml_potential import (
    MLIPElasticityDoc,
    MLIPEosDoc,
    MLIPPhononDoc,
    MLIPRelaxationDoc,
)
from emmet.core.utils import jsanitize
from maggma.builders.map_builder import MapBuilder
from maggma.core import Store
from matcalc.util import get_universal_calculator
from pymatgen.core import Structure


class MLIPBuilder(MapBuilder):
    def __init__(
        self, materials: Store, ml_potential: Store, calc_kwargs: dict = None, **kwargs
    ):
        """Machine learning interatomic potential builder.

        Args:
            materials: Store of oxidation states
            ml_potential: Store to update with bonding documents
            query : query on materials to limit search
        """
        self.materials = materials
        self.ml_potential = ml_potential
        self.kwargs = kwargs

        # Enforce that we key on material_id
        self.materials.key = "material_id"
        self.ml_potential.key = "material_id"
        super().__init__(
            source=materials,
            target=ml_potential,
            projection=["structure", "deprecated"],
            **kwargs,
        )

    def unary_function(self, item):
        struct = Structure.from_dict(item["structure"])
        mp_id, deprecated = item["material_id"], item["deprecated"]

        doc = {}
        doc_classes = (MLIPElasticityDoc, MLIPPhononDoc, MLIPRelaxationDoc, MLIPEosDoc)
        for model in ("CHGNet", "MEGNet"):
            calc = get_universal_calculator(model)
            for doc_cls in doc_classes:
                dct = doc_cls.from_structure(
                    structure=struct,
                    material_id=mp_id,
                    calc_kwargs={"calculator": calc},
                    deprecated=deprecated,
                )
                doc[model][doc_cls.property_name] = dct

        return jsanitize(doc, allow_bson=True)
