"""Task types and level of theory components for Jaguar calculations"""


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"

# This list reflects the calculations that have been completed at the time
# of the creation of these builders. These lists may be expanded over time.

TASK_TYPES = [
    "Single Point",
    "Geometry Optimization",
    "Frequency Analysis",
    "Transition State Geometry Optimization",
    "Intrinsic Reaction Coordinate",
    "Potential Energy Surface Scan",
    "Unknown",
]

FUNCTIONALS = ["PBE0", "CAM-B3LYP-D3", "wb97x-d", "wb97x-v", "M11"]

BASIS_SETS = ["def2-svpd(-f)", "def2-tzvppd(-g)"]

SOLVENT_MODELS = ["VACUUM", "PCM"]

SOLVENTS = ["WATER"]
