from importlib.metadata import version
from typing import TYPE_CHECKING, Union

from emmet.core.ml_potential import MLIPDoc
from emmet.core.utils import jsanitize
from maggma.builders.map_builder import MapBuilder
from maggma.core import Store
from matcalc.util import get_universal_calculator
from pymatgen.core import Structure

if TYPE_CHECKING:
    from ase.calculators.calculator import Calculator


class MLIPBuilder(MapBuilder):
    def __init__(
        self,
        materials: Store,
        ml_potential: Store,
        model: Union[str, "Calculator"],
        model_kwargs: dict = None,
        prop_kwargs: dict = None,
        **kwargs
    ):
        """Machine learning interatomic potential builder.

        Args:
            materials (Store): Materials to use as input structures.
            ml_potential (Store): Where to save MLIPDoc documents to.
            model (str | Calculator): ASE calculator or name of model to use as ML
                potential. See matcalc.util.UNIVERSAL_CALCULATORS for recognized names.
            model_kwargs (dict, optional): Additional kwargs to pass to the calculator.
                Defaults to None.
            prop_kwargs (dict, optional): One key for each matcalc PropCalc class.
                Recognized keys are RelaxCalc, ElasticityCalc, PhononCalc, EOSCalc.
                Defaults to None.
        """
        self.materials = materials
        self.ml_potential = ml_potential
        self.kwargs = kwargs
        self.model = get_universal_calculator(model, **(model_kwargs or {}))
        self.prop_kwargs = prop_kwargs or {}
        pkg_name = {"m3gnet": "matgl"}.get(model.lower(), model)
        self.provenance = dict(model=model, version=version(pkg_name))

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

        doc = MLIPDoc(
            structure=struct,
            material_id=mp_id,
            calculator=self.model,
            prop_kwargs=self.prop_kwargs,
            deprecated=deprecated,
        )
        doc.update(self.provenance)

        return jsanitize(doc, allow_bson=True)
