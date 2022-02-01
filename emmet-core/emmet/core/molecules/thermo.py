import logging
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Union
import copy

from typing_extensions import Literal

import numpy as np
from pydantic import Field
import networkx as nx

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender

from pymatgen.core.periodic_table import Specie, Element

from emmet.core.mpid import MPID
from emmet.core.qchem.task import TaskDocument
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


def get_free_energy(energy, enthalpy, entropy, temperature=298.15):
    """
    Helper function to calculate Gibbs free energy from electronic energy, enthalpy, and entropy

    :param energy: Electronic energy in Ha
    :param enthalpy: Enthalpy in kcal/mol
    :param entropy: Entropy in cal/mol-K
    :param temperature: Temperature in K. Default is 298.15, 25C

    returns: Free energy in eV

    """
    return energy * 27.2114 + enthalpy * 0.043363 - temperature * entropy * 0.000043363


