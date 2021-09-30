from math import ceil

from maggma.builders import Builder
from maggma.utils import grouper

from emmet.core.mpid import MPID
from emmet.core.summary import SummaryDoc
from emmet.core.utils import jsanitize


class SummaryBuilder(Builder):
    def __init__(
        self,
        materials,
        thermo,
        xas,
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
        summary,
        chunk_size=100,
        query=None,
        **kwargs,
    ):

        self.materials = materials
        self.thermo = thermo
        self.xas = xas
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
        self.summary = summary
        self.chunk_size = chunk_size
        self.query = query if query else {}

        super().__init__(
            sources=[
                materials,
                thermo,
                xas,
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

            data = {
                "materials": self.materials.query_one({self.materials.key: entry}),
                "thermo": self.thermo.query_one({self.thermo.key: entry}),
                "xas": list(self.xas.query({self.xas.key: entry})),
                "grain_boundaries": list(
                    self.grain_boundaries.query({self.grain_boundaries.key: entry})
                ),
                "electronic_structure": self.electronic_structure.query_one(
                    {self.electronic_structure.key: entry}
                ),
                "magnetism": self.magnetism.query_one({self.magnetism.key: entry}),
                "elasticity": self.elasticity.query_one({self.elasticity.key: entry}),
                "dielectric": self.dielectric.query_one({self.dielectric.key: entry}),
                "piezoelectric": self.piezoelectric.query_one(
                    {self.piezoelectric.key: entry}
                ),
                "phonon": self.phonon.query_one(
                    {self.phonon.key: entry}, [self.phonon.key]
                ),
                "insertion_electrodes": list(
                    self.insertion_electrodes.query(
                        {self.insertion_electrodes.key: entry},
                        [self.insertion_electrodes.key],
                    )
                ),
                "surface_properties": self.surfaces.query_one(
                    {self.surfaces.key: entry}
                ),
                "substrates": list(self.surfaces.query({self.substrates.key: entry})),
                "oxi_states": self.oxi_states.query_one({self.oxi_states.key: entry}),
                "eos": self.eos.query_one({self.eos.key: entry}, [self.eos.key]),
                "provenance": self.provenance.query_one({self.provenance.key: entry}),
            }

            sub_fields = {
                "magnetism": "magnetism",
                "dielectric": "dielectric",
                "piezoelectric": "piezo",
                "elasticity": "elasticity",
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

    def prechunk(self, number_splits: int):
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        keys = self.summary.newer_in(self.materials, criteria=q, exhaustive=True)

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.materials.key: {"$in": list(split)}}}

    def process_item(self, item):

        material_id = MPID(item["materials"]["material_id"])
        doc = SummaryDoc.from_docs(material_id=material_id, **item)
        return jsanitize(doc.dict(exclude_none=True), allow_bson=True)

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
