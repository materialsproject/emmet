from math import ceil
from typing import Dict, Iterator, List, Optional

import numpy as np
from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper
from pymatgen.core.structure import Structure

from emmet.core.absorption import AbsorptionDoc
from emmet.core.utils import jsanitize


class AbsorptionBuilder(Builder):
    def __init__(
        self,
        materials: Store,
        tasks: Store,
        absorption: Store,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        self.materials = materials
        self.tasks = tasks
        self.absorption = absorption
        self.query = query or {}
        self.kwargs = kwargs

        self.materials.key = "material_id"
        self.tasks.key = "task_id"
        self.absorption.key = "material_id"

        super().__init__(sources=[materials, tasks], targets=[absorption], **kwargs)

    def prechunk(self, number_splits: int) -> Iterator[Dict]:  # pragma: no cover
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        keys = self.absorption.newer_in(self.materials, criteria=q, exhaustive=True)

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.materials.key: {"$in": list(split)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process

        Returns:
            generator or list relevant tasks and materials to process
        """

        self.logger.info("Absorption Builder Started")

        q = dict(self.query)

        mat_ids = self.materials.distinct(self.materials.key, criteria=q)
        ab_ids = self.absorption.distinct(self.absorption.key)

        mats_set = set(self.absorption.newer_in(target=self.materials, criteria=q, exhaustive=True)) | (
            set(mat_ids) - set(ab_ids)
        )

        mats = [mat for mat in mats_set]

        self.logger.info("Processing {} materials for absorption data".format(len(mats)))

        self.total = len(mats)

        for mat in mats:
            doc = self._get_processed_doc(mat)

            if doc is not None:
                yield doc
            else:
                pass

    def process_item(self, item):
        structure = Structure.from_dict(item["structure"])
        mpid = item[self.materials.key]
        origin_entry = {"name": "absorption", "task_id": item["task_id"]}

        doc = AbsorptionDoc.from_structure(
            structure=structure,
            material_id=mpid,
            task_id=item["task_id"],
            deprecated=False,
            energies=item["energies"],
            real_d=item["real_dielectric"],
            imag_d=item["imag_dielectric"],
            absorption_co=item["optical_absorption_coeff"],
            bandgap=item["bandgap"],
            nkpoints=item["nkpoints"],
            last_updated=item["updated_on"],
            origins=[origin_entry],
        )

        return jsanitize(doc.dict(), allow_bson=True)

    def update_targets(self, items):
        """
        Inserts the new dielectric docs into the dielectric collection
        """
        docs = list(filter(None, items))

        if len(docs) > 0:
            self.logger.info(f"Found {len(docs)} absorption docs to update")
            self.absorption.update(docs)
        else:
            self.logger.info("No items to update")

    def _get_processed_doc(self, mat):

        mat_doc = self.materials.query_one(
            {self.materials.key: mat},
            [self.materials.key, "structure", "task_types", "run_types", "last_updated"],
        )

        task_types = mat_doc["task_types"].items()

        potential_task_ids = []

        for task_id, task_type in task_types:
            if task_type == "Optic":
                potential_task_ids.append(task_id)

        final_docs = []

        for task_id in potential_task_ids:
            task_query = self.tasks.query_one(
                properties=[
                    "orig_inputs.kpoints",
                    "orig_inputs.poscar.structure",
                    "input.parameters",
                    "input.structure",
                    "output.dielectric.energy",
                    "output.dielectric.real",
                    "output.dielectric.imag",
                    "output.optical_absorption_coeff",
                    "output.bandgap",
                ],
                criteria={self.tasks.key: task_id},
            )

            if task_query["output"]["optical_absorption_coeff"] is not None:

                try:
                    structure = task_query["orig_inputs"]["poscar"]["structure"]
                except KeyError:
                    structure = task_query["input"]["structure"]

                if (
                    task_query["orig_inputs"]["kpoints"]["generation_style"] == "Monkhorst"
                    or task_query["orig_inputs"]["kpoints"]["generation_style"] == "Gamma"
                ):
                    nkpoints = np.prod(task_query["orig_inputs"]["kpoints"]["kpoints"][0], axis=0)

                else:
                    nkpoints = task_query["orig_inputs"]["kpoints"]["nkpoints"]

                lu_dt = mat_doc["last_updated"]

                final_docs.append(
                    {
                        "task_id": task_id,
                        "nkpoints": int(nkpoints),
                        "energies": task_query["output"]["dielectric"]["energy"],
                        "real_dielectric": task_query["output"]["dielectric"]["real"],
                        "imag_dielectric": task_query["output"]["dielectric"]["imag"],
                        "optical_absorption_coeff": task_query["output"]["optical_absorption_coeff"],
                        "bandgap": task_query["output"]["bandgap"],
                        "structure": structure,
                        "updated_on": lu_dt,
                        self.materials.key: mat_doc[self.materials.key],
                    }
                )

        if len(final_docs) > 0:
            sorted_final_docs = sorted(
                final_docs,
                key=lambda entry: (
                    entry["nkpoints"],
                    entry["updated_on"],
                ),
                reverse=True,
            )
            return sorted_final_docs[0]
        else:
            return None
