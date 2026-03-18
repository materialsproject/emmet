"""Define analysis tools to featurize crystallographic data.

These modules are adapted from the following packages:
    - matminer: https://github.com/hackingmaterials/matminer/
        - Specifically, the `matminer.featurizers` module
    - robocrys: https://github.com/hackingmaterials/robocrystallographer
        - All modules except the CLI

Credits to the original authors:
    - matminer: Alex Dunn, Alireza Faghaninia, Anubhav Jain, Logan Ward, Nils E. R. Zimmermann
    - robocrys: Alex Ganose
Author accrediation and references can be found within those packages.
"""

try:
    # Use robocrys + matminer if installed
    from matminer.featurizers.base import BaseFeaturizer as Featurizer
    from robocrys import SiteStatsFingerprint, StructureCondenser, StructureDescriber
except ImportError:
    # Fall back to emmet if not installed.
    from emmet.core.featurization.featurizers import Featurizer, SiteStatsFingerprint
    from emmet.core.featurization.robocrys import StructureCondenser, StructureDescriber

__all__ = [
    "Featurizer",
    "SiteStatsFingerprint",
    "StructureCondenser",
    "StructureDescriber",
]
