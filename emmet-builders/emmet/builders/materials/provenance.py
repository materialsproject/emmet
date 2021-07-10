from collections import defaultdict
from itertools import chain
from typing import Dict, Iterable, List, Optional, Tuple

from maggma.core import Builder, Store
from maggma.utils import grouper
from pymatgen.analysis.structure_matcher import OrderDisorderElementComparator
from pymatgen.core import Structure
from pymatgen.util.provenance import StructureNL

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.provenance import ProvenanceDoc
from emmet.core.utils import group_structures


class ProvenanceBuilder(Builder):
    def __init__(
        self,
        materials: Store,
        provenance: Store,
        source_snls: List[Store],
        settings: Optional[EmmetBuildSettings] = None,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Creates provenance from source SNLs and materials

        Args:
            materials: Store of materials docs to tag with SNLs
            provenance: Store to update with provenance data
            source_snls: List of locations to grab SNLs
            query : query on materials to limit search
        """
        self.materials = materials
        self.provenance = provenance
        self.source_snls = source_snls
        self.settings = EmmetBuildSettings.autoload(settings)
        self.query = query or {}
        self.kwargs = kwargs

        materials.key = "material_id"
        provenance.key = "material_id"
        for s in source_snls:
            s.key = "snl_id"

        super().__init__(
            sources=[materials, *source_snls], targets=[provenance], **kwargs
        )

    def ensure_indicies(self):

        self.materials.ensure_index("material_id", unique=True)
        self.materials.ensure_index("formula_pretty")

        self.provenance.ensure_index("material_id", unique=True)
        self.provenance.ensure_index("formula_pretty")

        for s in self.source_snls:
            s.ensure_index("snl_id")
            s.ensure_index("formula_pretty")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:
        self.ensure_indicies()

        # Find all formulas for materials that have been updated since this
        # builder was last ran
        q = {**self.query, "property_name": ProvenanceDoc.property_name}
        updated_materials = self.provenance.newer_in(
            self.materials,
            criteria=q,
            exhaustive=True,
        )
        forms_to_update = set(
            self.materials.distinct(
                "formula_pretty", {"material_id": {"$in": updated_materials}}
            )
        )

        # Find all new SNL formulas since the builder was last run
        for source in self.source_snls:
            new_snls = self.provenance.newer_in(source)
            forms_to_update |= set(source.distinct("formula_pretty", new_snls))

        # Now reduce to the set of formulas we actually have
        forms_avail = set(self.materials.distinct("formula_pretty", self.query))
        forms_to_update = forms_to_update & forms_avail

        self.logger.info(
            f"Found {len(forms_to_update)} new/updated systems to distribute to workers "
            f"in chunks of {len(forms_to_update)/number_splits}"
        )

        for chunk in grouper(forms_to_update, number_splits):
            yield {"formula_pretty": {"$in": chunk}}

    def get_items(self) -> Tuple[List[Dict], List[Dict]]:
        """
        Gets all materials to assocaite with SNLs
        Returns:
            generator of materials and SNLs that could match
        """
        self.logger.info("Provenance Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indicies()

        # Find all formulas for materials that have been updated since this
        # builder was last ran
        q = {**self.query, "property_name": ProvenanceDoc.property_name}
        updated_materials = self.provenance.newer_in(
            self.materials,
            criteria=q,
            exhaustive=True,
        )
        forms_to_update = set(
            self.materials.distinct(
                "formula_pretty", {"material_id": {"$in": updated_materials}}
            )
        )

        # Find all new SNL formulas since the builder was last run
        for source in self.source_snls:
            new_snls = self.provenance.newer_in(source)
            forms_to_update |= set(source.distinct("formula_pretty", new_snls))

        # Now reduce to the set of formulas we actually have
        forms_avail = set(self.materials.distinct("formula_pretty", self.query))
        forms_to_update = forms_to_update & forms_avail

        self.logger.info(f"Found {len(forms_to_update)} new/updated systems to proces")

        self.total = len(forms_to_update)

        for formulas in grouper(forms_to_update, self.chunk_size):
            snls = []
            for source in self.source_snls:
                snls.extend(
                    source.query(criteria={"formula_pretty": {"$in": formulas}})
                )

            mats = list(
                self.materials.query(
                    properties=[
                        "material_id",
                        "last_updated",
                        "structure",
                        "initial_structures",
                        "formula_pretty",
                    ],
                    criteria={"formula_pretty": {"$in": formulas}},
                )
            )

            form_groups = defaultdict(list)
            for snl in snls:
                form_groups[snl["formula_pretty"]].append(snl)

            mat_groups = defaultdict(list)
            for mat in mats:
                mat_groups[mat["formula_pretty"]].append(mat)

            for formula, snl_group in form_groups.items():

                mat_group = mat_groups[formula]

                self.logger.debug(
                    f"Found {len(snl_group)} snls and {len(mat_group)} mats"
                )
                yield mat_group, snl_group

    def process_item(self, item) -> List[Dict]:
        """
        Matches SNLS and Materials
        Args:
            item (tuple): a tuple of materials and snls
        Returns:
            list(dict): a list of collected snls with material ids
        """
        mats, source_snls = item
        formula_pretty = mats[0]["formula_pretty"]
        snl_docs = list()
        self.logger.debug(f"Finding Provenance {formula_pretty}")

        # Match up SNLS with materials
        for mat in mats:
            matched_snls = list(self.match(source_snls, mat))
            if len(matched_snls) > 0:
                doc = ProvenanceDoc.from_SNLs(
                    material_id=mat["material_id"], snls=matched_snls
                )

                doc.authors.append(self.settings.DEFAULT_AUTHOR)
                doc.history.append(self.settings.DEFAULT_HISTORY)
                doc.references.append(self.settings.DEFAULT_REFERENCE)

                snl_docs.append(doc.dict(exclude_unset=True))

        return snl_docs

    def match(self, snls, mat):
        """
        Finds a material doc that matches with the given snl
        Args:
            snl ([dict]): the snls list
            mat (dict): a materials doc
        Returns:
            generator of materials doc keys
        """

        m_strucs = [Structure.from_dict(mat["structure"])] + [
            Structure.from_dict(init_struc) for init_struc in mat["initial_structures"]
        ]
        snl_strucs = []
        for snl in snls:
            struc = Structure.from_dict(snl)
            struc.snl = snl
            snl_strucs.append(struc)

        groups = group_structures(
            m_strucs + snl_strucs,
            ltol=self.settings.LTOL,
            stol=self.settings.STOL,
            angle_tol=self.settings.ANGLE_TOL,
            # comparator=OrderDisorderElementComparator(),
        )
        matched_groups = [
            group
            for group in groups
            if any(not hasattr(struc, "snl") for struc in group)
        ]
        snls = [
            struc.snl
            for group in matched_groups
            for struc in group
            if hasattr(struc, "snl")
        ]

        self.logger.debug(f"Found {len(snls)} SNLs for {mat['material_id']}")
        return snls

    def update_targets(self, items):
        """
        Inserts the new SNL docs into the SNL collection
        """

        snls = list(filter(None, chain.from_iterable(items)))

        if len(snls) > 0:
            self.logger.info(f"Found {len(snls)} SNLs to update")
            self.provenance.update(snls)
        else:
            self.logger.info("No items to update")
