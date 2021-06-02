from collections import defaultdict
from math import ceil

from maggma.builders import Builder
from maggma.utils import grouper

from emmet.core.mpid import MPID
from emmet.core.search import SearchDoc
from emmet.core.utils import jsanitize


class SearchBuilder(Builder):
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
        phonon,
        insertion_electrodes,
        substrates,
        surfaces,
        eos,
        search,
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
        self.phonon = phonon
        self.insertion_electrodes = insertion_electrodes
        self.substrates = substrates
        self.surfaces = surfaces
        self.eos = eos
        self.search = search
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
                phonon,
                insertion_electrodes,
                surfaces,
                substrates,
                eos,
            ],
            targets=[search],
            chunk_size=chunk_size,
            **kwargs,
        )

    def get_items(self):
        """
        Gets all items to process

        Returns:
            list of relevant materials and data
        """

        self.logger.info("Search Builder Started")

        q = dict(self.query)

        mat_ids = self.materials.distinct(field=self.materials.key, criteria=q)
        search_ids = self.search.distinct(field=self.search.key, criteria=q)

        search_set = set(mat_ids) - set(search_ids)

        search_list = [key for key in search_set]

        self.total = len(search_list)

        self.logger.debug("Processing {} materials.".format(self.total))

        for entry in search_list:

            data = {
                "materials": list(self.materials.query({self.materials.key: entry})),
                "thermo": list(self.thermo.query({self.thermo.key: entry})),
                "xas": list(self.xas.query({self.xas.key: entry})),
                "grain_boundaries": list(
                    self.grain_boundaries.query({self.grain_boundaries.key: entry})
                ),
                "electronic_structure": list(
                    self.electronic_structure.query(
                        {self.electronic_structure.key: entry}
                    )
                ),
                "magnetism": list(self.magnetism.query({self.magnetism.key: entry})),
                "elasticity": list(self.elasticity.query({self.elasticity.key: entry})),
                "dielectric": list(self.dielectric.query({self.dielectric.key: entry})),
                "phonon": list(
                    self.phonon.query({self.phonon.key: entry}, [self.phonon.key])
                ),
                "insertion_electrodes": list(
                    self.insertion_electrodes.query(
                        {self.insertion_electrodes.key: entry},
                        [self.insertion_electrodes.key],
                    )
                ),
                "surface_properties": list(
                    self.surfaces.query({self.surfaces.key: entry})
                ),
                "substrates": list(self.surfaces.query({self.substrates.key: entry})),
                "eos": list(self.eos.query({self.eos.key: entry}, [self.eos.key])),
            }

            yield data

    def prechunk(self, number_splits: int):
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        keys = self.search.newer_in(self.materials, criteria=q, exhaustive=True)

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.materials.key: {"$in": list(split)}}}

    def process_item(self, item):

        d = defaultdict(dict)

        # Materials

        materials_fields = [
            "nsites",
            "elements",
            "nelements",
            "composition",
            "composition_reduced",
            "formula_pretty",
            "formula_anonymous",
            "chemsys",
            "volume",
            "density",
            "density_atomic",
            "symmetry",
            "structure",
            "deprecated",
        ]

        ids = []

        for doc in item["materials"]:

            ids.append(doc[self.materials.key])
            d[ids[-1]] = defaultdict(dict)
            d[ids[-1]]["material_id"] = MPID(doc["material_id"])

            for field in materials_fields:
                d[ids[-1]][field] = doc[field]

        for id in ids:

            d[id]["has_props"] = set()

            # Thermo

            thermo_fields = [
                "uncorrected_energy_per_atom",
                "energy_per_atom",
                "formation_energy_per_atom",
                "energy_above_hull",
                "is_stable",
                "equillibrium_reaction_energy_per_atom",
                "decomposes_to",
            ]

            for doc in item["thermo"]:
                if doc[self.thermo.key] == id:
                    for field in thermo_fields:
                        d[id][field] = doc[field]

            # XAS

            xas_fields = ["absorbing_element", "edge", "spectrum_type", "xas_id"]

            for doc in item["xas"]:
                if doc[self.xas.key] == id:

                    if d[id].get("xas", None) is None:
                        d[id]["xas"] = []

                    d[id]["has_props"].add("xas")

                    d[id]["xas"].append({field: doc[field] for field in xas_fields})

            # GB

            gb_fields = ["gb_energy", "sigma", "type", "rotation_angle", "w_sep"]

            for doc in item["grain_boundaries"]:
                if doc[self.grain_boundaries.key] == id:

                    if d[id].get("grain_boundaries", None) is None:
                        d[id]["grain_boundaries"] = []

                    d[id]["has_props"].add("grain_boundaries")

                    d[id]["grain_boundaries"].append(
                        {field: doc[field] for field in gb_fields}
                    )

            # Electronic Structure + Bandstructure + DOS

            es_fields = [
                "band_gap",
                "efermi",
                "cbm",
                "vbm",
                "is_gap_direct",
                "is_metal",
            ]

            for doc in item["electronic_structure"]:
                if doc[self.electronic_structure.key] == id:
                    for field in es_fields:
                        d[id][field] = doc[field]

                    d[id]["es_source_calc_id"] = doc["calc_id"]

                    if doc["bandstructure"] is not None:
                        if any(doc["bandstructure"].values()):
                            d[id]["has_props"].add("bandstructure")
                            d[id]["bandstructure"] = doc["bandstructure"]

                    if doc["dos"] is not None:
                        d[id]["has_props"].add("dos")
                        d[id]["dos"] = doc["dos"]

            # Magnetism

            magnetism_fields = [
                "ordering",
                "total_magnetization",
                "total_magnetization_normalized_vol",
                "total_magnetization_normalized_formula_units",
            ]

            d[id]["spin_polarized"] = False

            for doc in item["magnetism"]:
                if doc[self.magnetism.key] == id:
                    d[id]["has_props"].add("magnetism")

                    d[id]["spin_polarized"] = True

                    for field in magnetism_fields:
                        d[id][field] = doc["magnetism"][field]

            # Elasticity

            elasticity_fields = [
                "k_voigt",
                "k_reuss",
                "k_vrh",
                "g_voigt",
                "g_reuss",
                "g_vrh",
                "universal_anisotropy",
                "homogeneous_poisson",
            ]

            for doc in item["elasticity"]:
                if doc[self.elasticity.key] == id:
                    d[id]["has_props"].add("elasticity")

                    for field in elasticity_fields:
                        d[id][field] = doc["elasticity"][field]

            # Dielectric and Piezo

            dielectric_fields = ["e_total", "e_ionic", "e_static", "n"]

            piezo_fields = ["e_ij_max"]

            for doc in item["dielectric"]:
                if doc[self.dielectric.key] == id:
                    check_dielectric = doc.get("dielectric", None)
                    check_piezo = doc.get("piezo", None)
                    if check_dielectric is not None and check_dielectric != {}:
                        d[id]["has_props"].add("dielectric")

                        for field in dielectric_fields:
                            d[id][field] = doc["dielectric"][field]

                    if check_piezo is not None and check_piezo != {}:
                        d[id]["has_props"].add("piezoelectric")

                        for field in piezo_fields:
                            d[id][field] = doc["piezo"][field]

            # Surface properties

            surface_fields = [
                "weighted_surface_energy",
                "weighted_surface_energy_EV_PER_ANG2",
                "shape_factor",
                "surface_anisotropy",
            ]

            for doc in item["surface_properties"]:
                if doc[self.surfaces.key] == id:
                    d[id]["has_props"].add("surface_properties")

                    for field in surface_fields:
                        d[id][field] = doc[field]

            # EOS

            for doc in item["eos"]:

                if doc[self.eos.key] == id:
                    d[id]["has_props"].add("eos")

            # Phonon

            for doc in item["phonon"]:

                if doc[self.phonon.key] == id:
                    d[id]["has_props"].add("phonon")

            # Insertion Electrodes

            for doc in item["insertion_electrodes"]:

                if doc[self.phonon.key] == id:
                    d[id]["has_props"].add("insertion_electrode")

            # Substrates

            for doc in item["substrates"]:

                if doc[self.substrates.key] == id:
                    d[id]["has_props"].add("substrates")

            d[id]["has_props"] = list(d[id]["has_props"])

        for mpid in d:
            d[mpid] = SearchDoc(**d[mpid])

        return d

    def update_targets(self, items):
        """
        Copy each search doc to the store

        Args:
            items ([dict]): A list of dictionaries of mpid document pairs to update
        """
        items = list(filter(None, items))

        docs = list([doc.dict(exclude_none=True) for doc in items[0].values()])

        if len(items) > 0:
            self.logger.info("Inserting {} search docs".format(len(docs)))
            self.search.update(docs=jsanitize(docs, allow_bson=True))
        else:
            self.logger.info("No search entries to update")
