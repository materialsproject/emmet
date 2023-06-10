from math import ceil

from maggma.builders import Builder
from maggma.utils import grouper

from emmet.core.mpid import MPID
from emmet.core.summary import SummaryDoc, HasProps
from emmet.core.utils import jsanitize
from emmet.core.thermo import ThermoType


class SummaryBuilder(Builder):
    def __init__(
        self,
        materials,
        thermo,
        xas,
        chemenv,
        absorption,
        grain_boundaries,
        electronic_structure,
        magnetism,
        elasticity,
        dielectric,
        piezoelectric,
        phonon,
        insertion_electrodes,
        substrates,
        surfaces,
        oxi_states,
        eos,
        provenance,
        charge_density_index,
        summary,
        thermo_type=ThermoType.GGA_GGA_U_R2SCAN.value,
        chunk_size=100,
        query=None,
        **kwargs,
    ):
        self.materials = materials
        self.thermo = thermo
        self.xas = xas
        self.chemenv = chemenv
        self.absorption = absorption
        self.grain_boundaries = grain_boundaries
        self.electronic_structure = electronic_structure
        self.magnetism = magnetism
        self.elasticity = elasticity
        self.dielectric = dielectric
        self.piezoelectric = piezoelectric
        self.phonon = phonon
        self.insertion_electrodes = insertion_electrodes
        self.substrates = substrates
        self.surfaces = surfaces
        self.oxi_states = oxi_states
        self.eos = eos
        self.provenance = provenance
        self.charge_density_index = charge_density_index

        self.thermo_type = thermo_type

        self.summary = summary
        self.chunk_size = chunk_size
        self.query = query if query else {}

        super().__init__(
            sources=[
                materials,
                thermo,
                xas,
                chemenv,
                absorption,
                grain_boundaries,
                electronic_structure,
                magnetism,
                elasticity,
                dielectric,
                piezoelectric,
                phonon,
                insertion_electrodes,
                surfaces,
                oxi_states,
                substrates,
                eos,
                provenance,
                charge_density_index,
            ],
            targets=[summary],
            chunk_size=chunk_size,
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

        self.logger.debug("Processing {} materials.".format(self.total))

        for entry in summary_set:
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
                HasProps.surface_properties.value: self.surfaces.query_one(
                    {self.surfaces.key: {"$in": all_tasks}}
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

            sub_fields = {
                HasProps.elasticity.value: "elasticity",
            }

            for collection, sub_field in sub_fields.items():
                if data[collection] is not None:
                    data[collection] = (
                        data[collection][sub_field]
                        if (sub_field in data[collection])
                        and (data[collection][sub_field] != {})
                        else None
                    )

            yield data

    def prechunk(self, number_splits: int):  # pragma: no cover
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        keys = self.summary.newer_in(self.materials, criteria=q, exhaustive=True)

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.materials.key: {"$in": list(split)}}}

    def process_item(self, item):
        material_id = MPID(item[HasProps.materials.value]["material_id"])
        doc = SummaryDoc.from_docs(material_id=material_id, **item)
        return jsanitize(doc.dict(exclude_none=False), allow_bson=True)

    def update_targets(self, items):
        """
        Copy each summary doc to the store

        Args:
            items ([dict]): A list of dictionaries of mpid document pairs to update
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Inserting {} summary docs".format(len(items)))
            self.summary.update(docs=items)
        else:
            self.logger.info("No summary entries to update")
