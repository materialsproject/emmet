"""Task types and level of theory components for Q-Chem calculations"""

from importlib.resources import files as import_resource_files
from monty.serialization import loadfn
import sys

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"

for attr, vals in loadfn(
    str(import_resource_files("emmet.core.qchem.calc_types") / "calc_types.yaml")
).items():
    setattr(sys.modules[__name__],attr,vals)

FUNCTIONALS = [
    rt
    for functionals in FUNCTIONAL_CLASSES.values()
    for rt in functionals
]