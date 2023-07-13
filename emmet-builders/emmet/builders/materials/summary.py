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
                [task_id for task_id, task_type in materials_doc["task_types"].items() if task_type == "Static"]
            ) - set(materials_doc["deprecated_tasks"])

            all_tasks = list(materials_doc["task_types"].keys())

            # HasProps-store mapping
            store_map = {
                HasProps.thermo.value: self.thermo,
                HasProps.xas.value: self.xas,
                HasProps.chemenv.value: self.chemenv,
                HasProps.absorption.value: self.absorption,
                HasProps.grain_boundaries.value: self.grain_boundaries,
                HasProps.electronic_structure.value: self.electronic_structure,
                HasProps.magnetism.value: self.magnetism,
                HasProps.elasticity.value: self.elasticity,
                HasProps.dielectric.value: self.dielectric,
                HasProps.piezoelectric.value: self.piezoelectric,
                HasProps.phonon.value: self.phonon,
                HasProps.insertion_electrodes.value: self.insertion_electrodes,
                HasProps.surface_properties.value: self.surfaces,
                HasProps.substrates.value: self.substrates,
                HasProps.oxi_states.value: self.oxi_states,
                HasProps.eos.value: self.eos,
                HasProps.provenance.value: self.provenance,
                HasProps.charge_density.value: self.charge_density_index,
            }

            data = {HasProps.materials.value: materials_doc}

            list_query_colls = [
                HasProps.xas.value,
                HasProps.grain_boundaries.value,
                HasProps.insertion_electrodes.value,
                HasProps.substrates.value,
            ]

            custom_args = {
                HasProps.thermo.value: ({self.materials.key: entry, "thermo_type": str(self.thermo_type)},),
                HasProps.phonon.value: (
                    {self.phonon.key: {"$in": all_tasks}},
                    [self.phonon.key],
                ),
                HasProps.insertion_electrodes.value: (
                    {"material_ids": entry},
                    [self.insertion_electrodes.key],
                ),
                HasProps.surface_properties.value: ({self.surfaces.key: {"$in": all_tasks}},),
                HasProps.elasticity.value: ({self.elasticity.key: {"$in": all_tasks}},),
                HasProps.eos.value: (
                    {self.eos.key: {"$in": all_tasks}},
                    [self.eos.key],
                ),
                HasProps.charge_density.value: (
                    {"task_id": {"$in": list(valid_static_tasks)}},
                    ["task_id"],
                ),
            }

            # Obtain docs or lists of docs used in SummaryDoc construction method
            for collection in store_map:
                custom_args_vals = custom_args.get(collection, None)

                if collection in list_query_colls:
                    args = custom_args_vals or ({store_map[collection].key: {"$in": all_tasks}},)

                    data[collection] = list(store_map[collection].query(*args))
                else:
                    args = custom_args_vals or ({store_map[collection].key: entry},)

                    data[collection] = store_map[collection].query_one(*args)

            # Handle subfields
            sub_fields = {HasProps.elasticity.value: "elasticity"}

            for collection, sub_field in sub_fields.items():
                if data[collection] is not None:
                    data[collection] = (
                        data[collection][sub_field]
                        if (sub_field in data[collection]) and (data[collection][sub_field] != {},)
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
