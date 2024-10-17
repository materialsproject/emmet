"""Task types and level of theory components for Q-Chem calculations"""

from importlib.resources import files as import_resource_files
from monty.serialization import loadfn

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"

_calc_type_config = loadfn(
    str(import_resource_files("emmet.core.qchem.calc_types") / "calc_types.yaml")
)

# NB: this would be easier with setattr but the following is less opaque
FUNCTIONAL_CLASSES = _calc_type_config.get("FUNCTIONAL_CLASSES")
TASK_TYPES = _calc_type_config.get("TASK_TYPES")
BASIS_SETS = _calc_type_config.get("BASIS_SETS")
SOLVENT_MODELS = _calc_type_config.get("SOLVENT_MODELS")

FUNCTIONALS = [rt for functionals in FUNCTIONAL_CLASSES.values() for rt in functionals]
