from math import ceil
from typing import Dict

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.mpid import MPID
from emmet.core.summary import HasProps, SummaryDoc
from emmet.core.thermo import ThermoType
from emmet.core.utils import jsanitize


class SummaryBuilder(Builder):
    def __init__(
        self,
        source_keys: Dict[str, Store],
        target_keys: Dict[str, Store],
        thermo_type=ThermoType.GGA_GGA_U_R2SCAN.value,
        chunk_size=100,
        allow_bson=True,
        query=None,
        **kwargs,
    ):
        self.source_keys = source_keys
        self.target_keys = target_keys

        self.absorption = source_keys["absorption"]
        self.charge_density_index = source_keys["charge_density_index"]
        self.chemenv = source_keys["chemenv"]
        self.dielectric = source_keys["dielectric"]
        self.elasticity = source_keys["elasticity"]
        self.electronic_structure = source_keys["electronic_structure"]
        self.eos = source_keys["eos"]
        self.grain_boundaries = source_keys["grain_boundaries"]
        self.insertion_electrodes = source_keys["insertion_electrodes"]
        self.magnetism = source_keys["magnetism"]
        self.materials = source_keys["materials"]
        self.oxi_states = source_keys["oxi_states"]
        self.phonon = source_keys["phonon"]
        self.piezoelectric = source_keys["piezoelectric"]
        self.provenance = source_keys["provenance"]
        self.substrates = source_keys["substrates"]
        self.surface_properties = source_keys["surface_properties"]
        self.thermo = source_keys["thermo"]
        self.xas = source_keys["xas"]

        self.thermo_type = thermo_type

        self.summary = target_keys["summary"]
        self.chunk_size = chunk_size
        self.allow_bson = allow_bson
        self.query = query if query else {}

        super().__init__(
            sources=[
                self.materials,
                self.thermo,
                self.xas,
                self.chemenv,
                self.absorption,
                self.grain_boundaries,
                self.electronic_structure,
                self.magnetism,
                self.elasticity,
                self.dielectric,
                self.piezoelectric,
                self.phonon,
                self.insertion_electrodes,
                self.surface_properties,
                self.oxi_states,
                self.substrates,
                self.eos,
                self.provenance,
                self.charge_density_index,
            ],
            targets=[self.summary],
            chunk_size=self.chunk_size,
            **kwargs,
        )

    def get_items(self):
        """
        Gets all items to process

        Returns:
            list of relevant materials and data
        """

        self.logger.info("Summary Builder Started")

        q = dict(self.query)

        mat_ids = self.materials.distinct(field=self.materials.key, criteria=q)
        summary_ids = self.summary.distinct(field=self.summary.key, criteria=q)

        summary_set = set(mat_ids) - set(summary_ids)

        self.total = len(summary_set)

        self.logger.debug(f"Processing {self.total} materials.")

        return [
            list(summary_set)[i : i + self.chunk_size]
            for i in range(0, self.total, self.chunk_size)
        ]

    def get_processed_docs(self, mats):
        for store in self.source_keys:
            self.source_keys[store].connect()

        all_docs = []

        for entry in mats:
            materials_doc = self.materials.query_one({self.materials.key: entry})

            valid_static_tasks = set(
                [
                    task_id
                    for task_id, task_type in materials_doc["task_types"].items()
                    if task_type == "Static"
                ]
            ) - set(materials_doc["deprecated_tasks"])

            all_tasks = list(materials_doc["task_types"].keys())

            data = {
                HasProps.materials.value: materials_doc,
                HasProps.thermo.value: self.thermo.query_one(
                    {self.materials.key: entry, "thermo_type": str(self.thermo_type)}
                ),
                HasProps.xas.value: list(
                    self.xas.query({self.xas.key: {"$in": all_tasks}})
                ),
                HasProps.grain_boundaries.value: list(
                    self.grain_boundaries.query({self.grain_boundaries.key: entry})
                ),
                HasProps.electronic_structure.value: self.electronic_structure.query_one(
                    {self.electronic_structure.key: entry}
                ),
                HasProps.magnetism.value: self.magnetism.query_one(
                    {self.magnetism.key: entry}
                ),
                HasProps.elasticity.value: self.elasticity.query_one(
                    {self.elasticity.key: {"$in": all_tasks}}
                ),
                HasProps.dielectric.value: self.dielectric.query_one(
                    {self.dielectric.key: entry}
                ),
                HasProps.piezoelectric.value: self.piezoelectric.query_one(
                    {self.piezoelectric.key: entry}
                ),
                HasProps.phonon.value: self.phonon.query_one(
                    {self.phonon.key: {"$in": all_tasks}},
                    [self.phonon.key],
                ),
                HasProps.insertion_electrodes.value: list(
                    self.insertion_electrodes.query(
                        {"material_ids": entry},
                        [self.insertion_electrodes.key],
                    )
                ),
                HasProps.surface_properties.value: self.surface_properties.query_one(
                    {self.surface_properties.key: {"$in": all_tasks}}
                ),
                HasProps.substrates.value: list(
                    self.substrates.query(
                        {self.substrates.key: {"$in": all_tasks}}, [self.substrates.key]
                    )
                ),
                HasProps.oxi_states.value: self.oxi_states.query_one(
                    {self.oxi_states.key: entry}
                ),
                HasProps.eos.value: self.eos.query_one(
                    {self.eos.key: {"$in": all_tasks}}, [self.eos.key]
                ),
                HasProps.chemenv.value: self.chemenv.query_one(
                    {self.chemenv.key: entry}
                ),
                HasProps.absorption.value: self.absorption.query_one(
                    {self.absorption.key: entry}
                ),
                HasProps.provenance.value: self.provenance.query_one(
                    {self.provenance.key: entry}
                ),
                HasProps.charge_density.value: self.charge_density_index.query_one(
                    {"task_id": {"$in": list(valid_static_tasks)}}, ["task_id"]
                ),
            }

            sub_fields = {}

            for collection, sub_field in sub_fields.items():
                if data[collection] is not None:
                    data[collection] = (
                        data[collection][sub_field]
                        if (sub_field in data[collection])
                        and (data[collection][sub_field] != {})
                        else None
                    )

            all_docs.append(data)

        for store in self.source_keys:
            self.source_keys[store].close()

        return all_docs

    def prechunk(self, number_splits: int):  # pragma: no cover
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        keys = self.summary.newer_in(self.materials, criteria=q, exhaustive=True)

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.materials.key: {"$in": list(split)}}}

    def process_item(self, items):
        docs = []
        for item in items:
            if not item:
                continue

            material_id = MPID(item[HasProps.materials.value]["material_id"])
            doc = SummaryDoc.from_docs(material_id=material_id, **item)
            docs.append(
                jsanitize(
                    doc.model_dump(exclude_none=False), allow_bson=self.allow_bson
                )
            )

        return docs

    def update_targets(self, items):
        """
        Copy each summary doc to the store

        Args:
            items ([dict]): A list of dictionaries of mpid document pairs to update
        """
        if not items:
            return

        self.summary.connect()

        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Inserting {} summary docs".format(len(items)))
            self.summary.update(docs=items)
        else:
            self.logger.info("No summary entries to update")

        self.summary.close()
