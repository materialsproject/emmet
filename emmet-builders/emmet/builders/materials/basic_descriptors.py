from __future__ import annotations

import numpy as np
from emmet.core.structure import StructureMetadata

# TODO:
# 1) ADD DOCUMENT MODEL
# 2) Add checking OPs present in current implementation of site fingerprints.
# 3) Complete documentation!!!
from maggma.builders import MapBuilder
from matminer.featurizers.composition import ElementProperty
from matminer.featurizers.site import CoordinationNumber, CrystalNNFingerprint
from pymatgen.analysis import local_env
from pymatgen.core.structure import Structure

__author__ = "Nils E. R. Zimmermann <nerz@lbl.gov>"

nn_target_classes = [
    "MinimumDistanceNN",
    "VoronoiNN",
    "CrystalNN",
    "JmolNN",
    "MinimumOKeeffeNN",
    "MinimumVIRENN",
    "BrunnerNN_reciprocal",
    "BrunnerNN_relative",
    "BrunnerNN_real",
    "EconNN",
]


class BasicDescriptorsBuilder(MapBuilder):
    def __init__(self, materials, descriptors, **kwargs):
        """Calculates site-based descriptors (e.g., coordination numbers
        with different near-neighbor finding approaches) for materials and
        runs statistics analysis on selected descriptor types
        (order parameter-based site fingerprints).  The latter is
        useful as a definition of a structure fingerprint
        on the basis of local coordination information.
        Furthermore, composition descriptors are calculated
        (Magpie element property vector).

        Args:
            materials (Store): Store of materials documents.
            descriptors (Store): Store of composition, site, and
                                 structure descriptor data such
                                 as tetrahedral order parameter or
                                 fraction of being 8-fold coordinated.
            mat_query (dict): dictionary to limit materials to be analyzed.
        """
        self.materials = materials
        self.descriptors = descriptors

        # Set up all targeted site descriptors.
        self.sds = {}
        for nn in nn_target_classes:
            nn_ = getattr(local_env, nn)
            k = f"cn_{nn}"
            self.sds[k] = CoordinationNumber(nn_(), use_weights="none")
            k = f"cn_wt_{nn}"
            self.sds[k] = CoordinationNumber(nn_(), use_weights="sum")
        self.all_output_pieces = {"site_descriptors": list(self.sds.keys())}
        self.sds["csf"] = CrystalNNFingerprint.from_preset(
            "ops", distance_cutoffs=None, x_diff_weight=None
        )
        self.all_output_pieces["statistics"] = ["csf"]

        # Set up all targeted composition descriptors.
        self.cds = {}
        self.cds["magpie"] = ElementProperty.from_preset("magpie")
        self.all_output_pieces["composition_descriptors"] = ["magpie"]

        self.all_output_pieces["meta"] = ["atomate"]

        super().__init__(
            source=materials, target=descriptors, projection=["structure"], **kwargs
        )

    def unary_function(self, item):
        """Calculates all basic descriptors for the structures.


        Args:
            item (dict): a dict with a task_id and a structure

        Returns:
            dict: a basic-descriptors dict
        """
        self.logger.debug(
            f"Calculating basic descriptors for {item[self.materials.key]}"
        )

        struct = Structure.from_dict(item["structure"])

        descr_doc = {"structure": struct.copy()}
        descr_doc["meta"] = StructureMetadata.from_structure(struct)
        try:
            comp_descr = [{"name": "magpie"}]
            labels = self.cds["magpie"].feature_labels()
            values = self.cds["magpie"].featurize(struct.composition)
            for label, value in zip(labels, values):
                comp_descr[0][label] = value
            descr_doc["composition_descriptors"] = comp_descr
        except Exception as e:
            self.logger.error("Failed getting Magpie descriptors: " "{}".format(e))
        descr_doc["site_descriptors"] = self.get_site_descriptors_from_struct(
            descr_doc["structure"]
        )
        descr_doc["statistics"] = self.get_statistics(descr_doc["site_descriptors"])
        descr_doc[self.descriptors.key] = item[self.materials.key]

        return descr_doc

    def get_site_descriptors_from_struct(self, structure):
        doc = {}

        # Compute descriptors.
        for k, sd in self.sds.items():
            try:
                d = []
                l = sd.feature_labels()
                for i, _s in enumerate(structure.sites):
                    d.append({"site": i})
                    for j, desc in enumerate(sd.featurize(structure, i)):
                        d[i][l[j]] = desc
                doc[k] = d

            except Exception as e:
                self.logger.error(
                    "Failed calculating {} site-descriptors: " "{}".format(k, e)
                )

        return doc

    def get_statistics(self, site_descr, fps=("csf",)):
        doc = {}

        # Compute site-descriptor statistics.
        for fp in fps:
            doc[fp] = {}
            try:
                n_site = len(site_descr[fp])
                tmp = {}
                for isite in range(n_site):
                    for l, v in site_descr[fp][isite].items():
                        if l not in list(tmp.keys()):
                            tmp[l] = []
                        tmp[l].append(v)
                d = []
                for k, l in tmp.items():
                    dtmp = {"name": k}
                    dtmp["mean"] = np.mean(tmp[k])
                    dtmp["std"] = np.std(tmp[k])
                    d.append(dtmp)
                doc[fp] = d

            except Exception as e:
                self.logger.error(
                    "Failed calculating statistics of site " "descriptors: {}".format(e)
                )

        return doc
