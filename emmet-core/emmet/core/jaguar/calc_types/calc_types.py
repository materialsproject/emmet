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

FUNCTIONAL_CLASSES = {
    "gga": [],
    "meta-gga": [],
    "hybrid-gga": [
        "PBE0",
        "CAM-B3LYP-D3",
        "wb97x-d",
        "wb97x-v"
    ],
    "hybrid-meta-gga": [
        "M11"
    ],
}

FUNCTIONALS = [
    rt
    for functional_class in FUNCTIONAL_CLASSES
    for rt in FUNCTIONAL_CLASSES[functional_class]
]

BASIS_SETS = [
    "def2-svpd(-f)",
    "def2-tzvppd(-g)"
]

SOLVENT_MODELS = ["VACUUM", "PCM"]

SOLVENTS = ["WATER"]