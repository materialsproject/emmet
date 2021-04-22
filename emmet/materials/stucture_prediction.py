from datetime import datetime

from maggma.builder import Builder

from pymatgen.core import Specie, Structure
from pymatgen.io.cif import CifWriter
from pymatgen.analysis.structure_prediction.substitutor import Substitutor
from pymatgen.analysis.structure_prediction.substitution_probability import (
    SubstitutionPredictor,
)
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.transformations.standard_transformations import (
    AutoOxiStateDecorationTransformation,
)
from pymatgen.analysis.diffraction.xrd import XRDCalculator

from itertools import combinations
from monty.json import jsanitize

__author__ = "Matthew McDermott <mcdermott@lbl.gov>"


class StructurePredictionBuilder(Builder):
    def __init__(self, structure_templates, requests, crystals, query=None, **kwargs):
        """
        Predict structures given a list of elements and their oxidation states.

        Args:
            structure_templates (Store): store of template structures to predict from
            requests (Store): store of structure prediction requests
            crystals (Store): predicted crystal structures and their info (XRD, spacegroup, etc.)
        """

        self.structure_templates = structure_templates
        self.requests = requests
        self.crystals = crystals
        self.query = query if query else {}
        self.kwargs = kwargs
        self.auto_oxi = AutoOxiStateDecorationTransformation()

        super().__init__(
            sources=[structure_templates, requests],
            targets=[requests, crystals],
            **kwargs,
        )

    def get_items(self):
        """
        Gets all structure predictions ready to run

        Returns:
            Generator of request and relevant structure templates to run structure prediction tasks
        """
        self.logger.info("Structure Prediction Builder started")

        requests = self.requests.query(criteria={"state": "READY"})

        for request in requests:
            elements = request["elements"]
            oxi_states = request["element_oxidation_states"]
            threshold = request["threshold"]
            max_num_subs = request["max_num_subs"]

            original_species = [
                Specie(e, o) for e, o in zip(elements, map(int, oxi_states))
            ]

            request["original_species"] = original_species

            all_chemsys_to_consider = list(
                self.find_all_chemsys(original_species, threshold, max_num_subs)
            )
            self.logger.info(
                f"Considering the following chemical systems: {all_chemsys_to_consider}"
            )

            templates = [
                struct
                for struct in self.structure_templates.query(
                    {"chemsys": {"$in": all_chemsys_to_consider}}
                )
            ]

            self.logger.info(
                f"Acquired {len(templates)} structure templates for {original_species}"
            )

            yield {"request": request, "templates": templates}

    def process_item(self, item):
        """
        Finds all predicted structures for given item

        Args:
            item (dict): structure prediction request and relevant oxidation state-labeled structure templates

        Returns:
            (dict, dict): A tuple containing updated request doc and a list of crystal docs to update
        """
        request = item["request"]
        templates = item["templates"]

        self.logger.info(
            f"Labeling oxidation states for {len(templates)} structure templates"
        )

        oxi_labeled_templates = []
        for template in templates:
            struct = Structure.from_dict(template["structure"])
            try:
                oxi_labeled_templates.append(
                    {
                        "structure": self.auto_oxi.apply_transformation(struct),
                        "id": template[self.structure_templates.key],
                    }
                )
            except:
                continue  # if auto-oxidation fails, try next structure

        self.logger.info(
            f"Successfully labeled oxidation states for {len(oxi_labeled_templates)} structures"
        )
        self.logger.info("Substituting original species into structures")

        predicted_structs = Substitutor(
            threshold=request["threshold"]
        ).pred_from_structures(
            request["original_species"],
            oxi_labeled_templates,
            remove_duplicates=True,
            remove_existing=True,
        )
        predicted_structs.sort(key=lambda s: s.other_parameters["proba"], reverse=True)

        structure_prediction_id = request[self.requests.key]

        crystal_docs = []
        summaries = []

        self.logger.info(
            f"Found {len(predicted_structs)} predicted structures. Generating crystal docs (XRDs, CIFs, etc."
        )

        for number_id, struct in enumerate(predicted_structs):
            crystal = {}
            summary = {}
            xrd_dict = {}

            final_structure = struct.final_structure
            sga = SpacegroupAnalyzer(final_structure, symprec=0.1)

            for rad_source in ["CuKa", "AgKa", "MoKa", "FeKa"]:
                xrdc = XRDCalculator(wavelength=rad_source)
                pattern = xrdc.get_pattern(final_structure, two_theta_range=None)
                xrd_dict[rad_source] = pattern

            transformed_structure = struct.to_snl(
                f"{request['name']} <{request['email']}>",
                remarks=["Created by MP Structure Predictor"],
            )

            crystal[self.requests.key] = structure_prediction_id
            crystal[self.crystals.key] = number_id
            crystal["probability"] = struct.other_parameters["proba"]
            crystal["transformed_structure"] = transformed_structure
            crystal["xrd"] = xrd_dict
            crystal["space_group_info"] = {
                "symbol": sga.get_space_group_symbol(),
                "number": sga.get_space_group_number(),
                "hall": sga.get_hall(),
                "crystal_system": sga.get_crystal_system(),
            }

            summary[self.crystals.key] = number_id
            summary["probability"] = struct.other_parameters["proba"]
            summary["pretty_formula"] = final_structure.composition.reduced_formula
            summary["nsites"] = len(final_structure)
            summary["space_group"] = sga.get_space_group_symbol()
            summary["cif"] = str(CifWriter(final_structure))

            crystal_docs.append(jsanitize(crystal, strict=True))
            summaries.append(jsanitize(summary, strict=True))

        self.logger.info(
            f"Successfully generated {len(crystal_docs)} crystal docs for request {request['original_species']}"
        )

        request.update(
            {
                "state": "COMPLETE",
                "completed_at": datetime.utcnow(),
                "num_crystals": len(crystal_docs),
                "crystals": summaries,
            }
        )

        return request, crystal_docs

    def update_targets(self, items):
        """
        Update the request doc and insert the predicted crystals into the collection

        Args:
            items [(dict, dict)]: A list containing tuples with request, crystal docs to update
        """
        request_docs = []
        crystal_docs = []

        for item in items:
            request_docs.append(item[0])
            crystal_docs.extend(item[1])

        if len(request_docs) > 0:
            self.logger.info(f"Updating {len(request_docs)} request docs")
            self.requests.update(request_docs)
        else:
            self.logger.info("No requests to update")

        if len(crystal_docs) > 0:
            self.logger.info(f"Updating {len(crystal_docs)} crystal docs")
            self.crystals.update(
                crystal_docs, key=[self.requests.key, self.crystals.key]
            )
        else:
            self.logger.info("No crystals to update")

    @staticmethod
    def find_all_chemsys(original_species, threshold=0.0001, max_num_subs=5):
        """
        Determines chemical systems to consider via data-mined ionic substitution probabilities (see lambda.json)

        Args:
            original_species (list): a list of species, e.g. [Specie('Li',1), Specie('Ni',2), Specie('O',-2)]
            threshold (float): Probability threshold for generating ionic substitutions. Defaults to 0.0001
            max_num_subs (int): Limits maximum number of substitutions wanted. Defaults to 5

        Returns:
            (set): A set of all chemical systems to predict from
        """
        num_species = len(original_species)

        sub_elems = set()
        for specie in original_species:
            subs = SubstitutionPredictor(threshold=threshold).list_prediction([specie])

            # sort and cap number of substitutions
            subs.sort(key=lambda x: x["probability"], reverse=True)
            subs = subs[0:max_num_subs]

            for sub in subs:
                for new_species in sub["substitutions"]:
                    sub_elems.add(new_species.element)

        all_chemsys = set()
        for chemsys in combinations(sub_elems, num_species):
            all_chemsys.add("-".join(sorted([str(el) for el in chemsys])))

        return all_chemsys
