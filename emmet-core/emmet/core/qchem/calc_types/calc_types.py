"""Task types and level of theory components for Q-Chem calculations"""

import yaml
from importlib.resources import files

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"

with files("emmet.core.qchem.calc_types").joinpath("calc_types.yaml").open() as f:
    _calc_type_config = yaml.safe_load(f)

# NB: this would be easier with setattr but the following is less opaque
FUNCTIONAL_CLASSES = _calc_type_config.get("FUNCTIONAL_CLASSES")
TASK_TYPES = _calc_type_config.get("TASK_TYPES")
BASIS_SETS = _calc_type_config.get("BASIS_SETS")
SOLVENT_MODELS = _calc_type_config.get("SOLVENT_MODELS")

FUNCTIONALS = [rt for functionals in FUNCTIONAL_CLASSES.values() for rt in functionals]
