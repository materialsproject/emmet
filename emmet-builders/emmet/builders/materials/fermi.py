import resource
from math import ceil
from typing import Dict, Iterator, Optional

from maggma.core import Builder, Store
from maggma.utils import grouper

from emmet.core.fermi import FermiDoc
from emmet.core.utils import jsanitize

from pymatgen.core.structure import Structure
from pymatgen.electronic_structure.bandstructure import BandStructure


class FermiBuilder(Builder):
    def __init__(
        self,
        electronic_structures: Store,
        tasks: Store,
        bandstructures: Store,
        fermi_surfaces: Store,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Constructs ifermi fermi surfaces objects for materials from
        pymatgen bandstructure objects.

        Args:
            electronic_store (Store): Store of electronic struture documents to match to
            tasks (Store): Store of task documents for retrieving structure data
            bandstructures (Store): Store of bandstructure data in the form of
                pymatgen bandstructure objects
            fermi_surfaces (Store): Store of ifermi fermi surface objects to use
                in the construction of fermi surfaces
            query (dict): dictionary to limit materials to be analyzed

        """

        self.electronic_structures = electronic_structures
        self.tasks = tasks
        self.bandstructures = bandstructures
        self.fermi_surfaces = fermi_surfaces
        self.query = query or {}
        self.kwargs = kwargs

        self.electronic_structures.key = "material_id"
        self.tasks.key = "task_id"
        self.bandstructures.key = "fs_id"
        self.fermi_surfaces.key = "material_id"

        super().__init__(
            sources=[electronic_structures, tasks, bandstructures],
            targets=[fermi_surfaces],
            **kwargs,
        )

    def prechunk(self, number_splits: int) -> Iterator[Dict]:  # pragma: no cover
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        keys = self.fermi_surfaces.newer_in(
            self.electronic_structures, criteria=q, exhaustive=True
        )

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.electronic_structures.key: {"$in": list(split)}}}

    def get_items(self):
        """
        Gets all items to process

        Returns:
            Generator or list of relevant materials
        """

        self.logger.info("Fermi Builder Started")

        q = dict(self.query)

        q.update({"deprecated": False})

        elec_structure_ids = self.electronic_structures.distinct(
            self.electronic_structures.key, criteria=q
        )

        fermi_ids = self.fermi_surfaces.distinct(self.fermi_surfaces.key)

        mats_set = set(
            self.fermi_surfaces.newer_in(
                target=self.electronic_structures, criteria=q, exhaustive=True
            )
        ) | (set(elec_structure_ids) - set(fermi_ids))

        mats = [mat for mat in mats_set]

        self.total = len(mats)

        self.logger.info(f"Processing {self.total} items for fermi surface data")

        for mat in mats:
            doc = self._get_processed_doc(mat)

            if doc is not None:
                yield doc
            else:
                pass

    def process_item(self, item):
        try:
            fermi_doc = FermiDoc.from_structure(
                material_id=item["material_id"],
                task_id=item["task_id"],
                bandstructure=item["bandstructure"],
                last_updated=item["last_updated"],
            )
        except Exception as error:
            self.logger.warning(
                f"Error in generating fermi surfaces for {item['material_id']}: {error}"
            )
            return None

        # Default summary data
        data = dict(
            band_gap=item["band_gap"],
            cbm=item["cbm"],
            vbm=item["vbm"],
            efermi=item["efermi"],
            is_gap_direct=item["is_gap_direct"],
            is_metal=item["is_metal"],
            magnetic_ordering=item["magnetic_ordering"],
            elements=item["elements"],
            formula_pretty=item["formula_pretty"],
            chemsys=item["chemsys"],
            symmetry=item["symmetry"],
            last_updated=item["last_updated"],
            deprecated=item["deprecated"],
            fs_id=item["fs_id"],
            state=item["state"],
        )

        data.update(fermi_doc.dict())

        doc = jsanitize(data, allow_bson=True)

        return doc

    def update_targets(self, items):
        """
        Inserts the new fermi surface docs into the fermi_surface collection
        """
        docs = list(filter(None, items))

        if len(docs) > 0:
            self.logger.info(f"Found {len(docs)} fermi surface docs to update")
            self.fermi_surfaces.update(docs)
        else:
            self.logger.info("No items to update")

    def _get_processed_doc(self, mat):
        mat_doc = self.electronic_structures.query_one(
            criteria={self.electronic_structures.key: mat},
            properties=[
                self.electronic_structures.key,
                "task_id",
                "last_updated",
                "band_gap",
                "cbm",
                "vbm",
                "efermi",
                "is_gap_direct",
                "is_metal",
                "magnetic_ordering",
                "elements",
                "formula_pretty",
                "chemsys",
                "symmetry",
                "deprecated",
            ],
        )

        task_id = mat_doc["task_id"]

        task_query = self.tasks.query_one(
            criteria={"task_id": task_id},
            properties=["output", "state"],
        )

        bs_query = self.bandstructures.query_one(
            criteria={"task_id": task_id}, properties=["fs_id", "data"]
        )

        if bs_query:
            bandstructure = BandStructure.from_dict(bs_query["data"])
            if not bandstructure.structure:
                bandstructure.structure = Structure.from_dict(
                    task_query["output"]["structure"]
                )
        else:
            return None

        mat_doc.update(
            {
                self.electronic_structures.key: mat_doc[self.electronic_structures.key],
                "bandstructure": bandstructure,
                "fs_id": bs_query["fs_id"],
                "state": task_query["state"],
            }
        )

        return mat_doc
