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

from emmet.core.featurization.featurizers import Featurizer, SiteStatsFingerprint

__all__ = ["Featurizer", "SiteStatsFingerprint"]