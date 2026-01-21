"""Basic schematic of a featurizer.

Adapted from `matminer.featurizers.base`
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from pymatgen.analysis.local_env import CrystalNN, LocalStructOrderParams, CN_OPT_PARAMS
from pymatgen.core import Structure

if TYPE_CHECKING:
    from typing import Any, Literal
    from typing_extensions import Self

VALID_STAT_NAMES = {"mean", "maximum", "minimum", "std_dev"}

CN_TARGET_MOTIF_OP: dict[int, list[str]] = {
    1: ["sgl_bd"],
    2: ["L-shaped", "water-like", "bent 120 degrees", "bent 150 degrees", "linear"],
    3: ["trigonal planar", "trigonal non-coplanar", "T-shaped"],
    4: [
        "square co-planar",
        "tetrahedral",
        "rectangular see-saw-like",
        "see-saw-like",
        "trigonal pyramidal",
    ],
    5: ["pentagonal planar", "square pyramidal", "trigonal bipyramidal"],
    6: ["hexagonal planar", "octahedral", "pentagonal pyramidal"],
    7: ["hexagonal pyramidal", "pentagonal bipyramidal"],
    8: ["body-centered cubic", "hexagonal bipyramidal"],
    9: ["q2", "q4", "q6"],
    10: ["q2", "q4", "q6"],
    11: ["q2", "q4", "q6"],
    12: ["cuboctahedral", "q2", "q4", "q6"],
}


@dataclass
class Featurizer(ABC):
    """Abstract class to calculate features from structural input data."""

    @abstractmethod
    def featurize(self, *args, **kwargs) -> list[Any]:
        """
        Main featurizer function, which has to be implemented
        in any derived featurizer subclass.

        Args:
            x: input data to featurize (type depends on featurizer).

        Returns:
            (list) one or more features.
        """

        raise NotImplementedError("`featurize` is not defined!")

    @property
    @abstractmethod
    def feature_labels(self) -> list[str]:
        """
        Generate feature labels.

        Returns:
            list of str, the labels of the features
        """

        raise NotImplementedError("`feature_labels` is not defined!")


@dataclass
class CrystalNNFingerprint(Featurizer):
    """
    A local order parameter fingerprint for periodic crystals.

    Adapted from `matminer.featurizers.site.fingerprint`.

    The fingerprint represents the value of various order parameters for the
    site. The "wt" order parameter describes how consistent a site is with a
    certain coordination number. The remaining order parameters are computed
    by multiplying the "wt" for that coordination number with the OP value.

    The chem_info parameter can be used to also get chemical descriptors that
    describe differences in some chemical parameter (e.g., electronegativity)
    between the central site and the site neighbors.

    Args:
        op_types (dict): a dict of coordination number (int) to a list of str
            representing the order parameter types
        chem_info (dict): a dict of chemical properties (e.g., atomic mass)
            to dictionaries that map an element to a value
            (e.g., chem_info["Pauling scale"]["O"] = 3.44)
    """

    op_types: dict[int, list[str]] = field(default_factory=dict)
    chem_info: dict[str, dict[str, Any]] | None = None
    crystalnn: CrystalNN = field(default_factory=CrystalNN)
    _ops: dict[int, list[str | LocalStructOrderParams]] | None = None

    @classmethod
    def from_preset(cls, preset: Literal["cn", "ops"], **kwargs) -> Self:
        """
        Use preset parameters to get the fingerprint
        Args:
            preset ('cn' | 'ops'): Initializes the featurizer to use coordination number ('cn') or structural
                order parameters like octahedral, tetrahedral ('ops').
            **kwargs: other settings to be passed into CrystalNN class
        """
        cnn = CrystalNN(**kwargs)
        if preset == "cn":
            return cls(op_types={k + 1: ["wt"] for k in range(24)}, crystalnn=cnn)

        elif preset == "ops":
            return cls(
                op_types={
                    k: ["wt"] + CN_TARGET_MOTIF_OP.get(k, []) for k in range(1, 25)
                },
                chem_info=None,
                crystalnn=cnn,
            )

        raise ValueError(
            f"preset `{preset}` is not supported in `CrystalNNFingerprint`"
        )

    @property
    def chem_props(self) -> list[str]:
        return list((self.chem_info or {}).keys())

    @property
    def ops(self) -> dict[int, list[str | LocalStructOrderParams]]:
        if not self._ops:
            self._ops = {}  # load order parameter objects & parameters
            for cn, t_list in self.op_types.items():
                self._ops[cn] = []
                for t in t_list:
                    if t == "wt":
                        self._ops[cn].append(t)
                    else:
                        ot = t
                        p = None
                        if cn in CN_OPT_PARAMS.keys():
                            if t in CN_OPT_PARAMS[cn].keys():
                                ot = CN_OPT_PARAMS[cn][t][0]  # type: ignore[assignment]
                                if len(CN_OPT_PARAMS[cn][t]) > 1:
                                    p = CN_OPT_PARAMS[cn][t][1]
                        self._ops[cn].append(
                            LocalStructOrderParams([ot], parameters=[p])  # type: ignore[list-item]
                        )
        return self._ops

    def featurize(self, struct: Structure, idx: int) -> list[float]:
        """
        Get crystal fingerprint of site with given index in input
        structure.
        Args:
            struct (Structure): Pymatgen Structure object.
            idx (int): index of target site in structure.
        Returns:
            list of weighted order parameters of target site.
        """

        nndata = self.crystalnn.get_nn_data(struct, idx)
        max_cn = sorted(self.op_types)[-1]

        cn_fingerprint = []

        if self.chem_info is not None:
            prop_delta = {}  # dictionary of chemical property to final value
            for prop in self.chem_props:
                prop_delta[prop] = 0
            sum_wt = 0
            elem_central = struct.sites[idx].specie.symbol
            specie_central = str(struct.sites[idx].specie)

        for k in range(max_cn):
            cn = k + 1
            wt = nndata.cn_weights.get(cn, 0)
            if cn in self.ops:
                for op in self.ops[cn]:
                    if op == "wt":
                        cn_fingerprint.append(wt)

                        if self.chem_info is not None and wt != 0:
                            # Compute additional chemistry-related features
                            sum_wt += wt
                            neigh_sites = [d["site"] for d in nndata.cn_nninfo[cn]]

                            for prop in self.chem_props:
                                # get the value for specie, if not fall back to
                                # value defined for element
                                prop_central = self.chem_info[prop].get(
                                    specie_central,
                                    self.chem_info[prop].get(elem_central),
                                )

                                for neigh in neigh_sites:
                                    elem_neigh = neigh.specie.symbol
                                    specie_neigh = str(neigh.specie)
                                    prop_neigh = self.chem_info[prop].get(
                                        specie_neigh,
                                        self.chem_info[prop].get(elem_neigh),
                                    )

                                    prop_delta[prop] += (
                                        wt * (prop_neigh - prop_central) / cn  # type: ignore[operator]
                                    )

                    elif wt == 0:
                        cn_fingerprint.append(wt)
                    elif isinstance(op, LocalStructOrderParams):
                        neigh_sites = [d["site"] for d in nndata.cn_nninfo[cn]]
                        opval = op.get_order_parameters(
                            [struct[idx]] + neigh_sites,  # type: ignore[arg-type]
                            0,
                            indices_neighs=[i for i in range(1, len(neigh_sites) + 1)],
                        )[0]
                        opval = opval or 0  # handles None
                        cn_fingerprint.append(wt * opval)

        chem_fingerprint: list[float] = []

        if self.chem_info is not None:
            for val in prop_delta.values():
                chem_fingerprint.append(val / sum_wt)

        return cn_fingerprint + chem_fingerprint

    @property
    def feature_labels(self):
        labels = []
        max_cn = sorted(self.op_types)[-1]
        for k in range(max_cn):
            cn = k + 1
            if cn in list(self.ops.keys()):
                for op in self.op_types[cn]:
                    labels.append(f"{op} CN_{cn}")
        if self.chem_info is not None:
            for prop in self.chem_props:
                labels.append(f"{prop} local diff")
        return labels


@dataclass
class SiteStatsFingerprint(Featurizer):
    """Computes statistics of properties across all sites in a structure.

    Adapted and simplified significantly from `matminer.featurizers.structure.sites`.

    Args:
        site_featurizer : `Featurizer`
            Featurization to use on each site of a structure.
        stats : list of str
            Should be a list of stats in `VALID_STAT_NAMES`
    """

    site_featurizer: Featurizer = field(
        default_factory=lambda: CrystalNNFingerprint.from_preset(
            "ops",
            distance_cutoffs=None,
            x_diff_weight=None,
        )
    )
    stats: list[str] = field(default_factory=lambda: ["mean", "maximum"])

    @staticmethod
    def get_stat(op: Literal[*VALID_STAT_NAMES], vals: list[float]) -> float:  # type: ignore[valid-type]
        """Compute statistics of a 1-D array.

        Args:
            op : "mean", "maximum", "minimum", or "std_dev"
                A statistic name to compute
            vals : list[float]
                An ordered list of floats
        Returns:
            float, the statistic
        """
        v = np.array(vals)
        match op:
            case "mean":
                return v.mean()
            case "maximum":
                return v.max()
            case "minimum":
                return v.min()
            case "std_dev":
                return v.std()
            case _:
                raise ValueError(f"Unknown operation {op}")

    def featurize(self, s: Structure) -> list[float]:
        # Get each feature for each site
        vals: list[list[float]] = [[] for t in self.site_featurizer.feature_labels]
        for i, site in enumerate(s.sites):
            opvalstmp = self.site_featurizer.featurize(s, i)
            for j, opval in enumerate(opvalstmp):
                vals[j].append(0.0 if opval is None else opval)

        # If the user does not request statistics, return the site features now
        if self.stats is None:
            return vals

        # Compute the requested statistics
        return [self.get_stat(stat, v) for v in vals for stat in self.stats]  # type: ignore[arg-type]

    @property
    def feature_labels(self) -> list[str]:
        orig_feature_labels = self.site_featurizer.feature_labels
        if self.stats:
            labels = []
            # Make labels associated with the statistics
            for attr in orig_feature_labels:
                for stat in self.stats:
                    labels.append(f"{stat} {attr}")
            return labels
        return orig_feature_labels
