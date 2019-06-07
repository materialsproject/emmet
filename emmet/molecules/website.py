import os
from datetime import datetime
from itertools import chain, groupby
import numpy as np
import networkx as nx

from pymatgen import Molecule
from pymatgen.analysis.graphs import MoleculeGraph, isomorphic
from pymatgen.analysis.local_env import OpenBabelNN

from maggma.builders import Builder

from emmet.qchem.task_tagger import task_type
from emmet.common.utils import load_settings
from pydash.objects import get, set_, has

__author__ = "Sam Blau"


class WebsiteMoleculesBuilder(Builder):
    def __init__(self,
                 molecules,
                 redox,
                 website,
                 query=None,
                 **kwargs):
        """
        Calculates electrochemical and redox properties for molecules

        Args:
            molecules (Store): Store of molecules documents
            redox (Store): Store of electrochemical and redox data
            query (dict): dictionary to limit molecules to be analyzed
        """

        self.molecules = molecules
        self.redox = redox
        self.website = website
        self.query = query if query else {}
        super().__init__(sources=[molecules,redox], targets=[website], **kwargs)

    def get_items(self):
        """
        Gets sets of entries from formula_alphabetical that need to be processed

        Returns:
            generator of relevant entries from one formula_alphabetical
        """

        self.logger.info("Website molecules builder started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        redox_task_ids = self.redox.distinct(self.redox.key, {"charge":0, "$or":[{"IE":{"$exists":1}}, {"EA":{"$exists":1}}]})

        self.logger.info(
            "Found {} molecules with redox properties".format(len(redox_task_ids))
        )
        self.total = len(redox_task_ids)

        for t_id in redox_task_ids:
            mol = self.molecules.query_one({self.molecules.key:t_id})
            mol.update(self.redox.query_one({self.redox.key:t_id}))
            yield mol

    def process_item(self, item):
        """
        Process the an entries into a website doc

        Args:
            item entry: a smashed molecule + redox doc

        Returns:
            doc: a website doc
        """

        doc = []

        self.logger.debug(
            f"Procesing {len(item)} entries for {item[0]['formula_alphabetical']}"
        )

        # grouped_molecules = group_molecules_and_sort_by_charge(item)

        # for group in grouped_molecules:
        #     group_docs = []
        #     # Calculating the Gibbs free energy of each molecule
        #     for mol in group:
        #         doc = {self.redox.key:mol[self.molecules.key],"charge":mol["molecule"]["charge"],"last_updated":mol["last_updated"]}
        #         doc["gibbs"] = {}
        #         required_vals = ["vacuum_energy","vacuum_enthalpy","vacuum_entropy","solvated_energy","solvated_enthalpy","solvated_entropy"]
        #         missing_keys = [k for k in required_vals if k not in mol]
        #         if len(missing_keys) > 0:
        #             doc["_warnings"] = ["missing energy keys: {}".format(missing_keys)]
        #         if "vacuum_energy" in mol:
        #             doc["gibbs"]["vacuum"] = mol["vacuum_energy"]*27.21139+0.0433641*mol.get("vacuum_enthalpy",0.0)-298*mol.get("vacuum_entropy",0.0)*0.0000433641
        #         if "solvated_energy" in mol:
        #             doc["gibbs"]["solvated"] = mol["solvated_energy"]*27.21139+0.0433641*mol.get("solvated_enthalpy",0.0)-298*mol.get("solvated_entropy",0.0)*0.0000433641
        #         group_docs.append(doc)
        #     # Calculating ionization energy and electron affinity if multiple charges present
        #     if len(group_docs) > 1:
        #         for ii,doc in enumerate(group_docs):
        #             redox = {}
        #             if ii != len(group_docs)-1:
        #                 # check charge diff = 1
        #                 redox["IE"] = {}
        #                 for key in doc["gibbs"]:
        #                     if key in group_docs[ii+1]["gibbs"]:
        #                         redox["IE"][key] = group_docs[ii+1]["gibbs"][key] - doc["gibbs"][key]
        #             if ii != 0:
        #                 # check charge diff = 1
        #                 redox["EA"] = {}
        #                 for key in doc["gibbs"]:
        #                     if key in group_docs[ii-1]["gibbs"]:
        #                         redox["EA"][key] = doc["gibbs"][key] - group_docs[ii-1]["gibbs"][key]
        #             doc["redox"] = redox
        #     # Calculating redox potentials if IE and / or EA present



        #     docs.extend(group_docs)
        # print(docs)
        return doc

    def update_targets(self, items):
        """
        Inserts the redox docs into the redox collection

        Args:
            items ([[dict]]): a list of lists of redox dictionaries to update
        """
        # flatten out lists
        items = list(filter(None))

        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info("Updating {} website documents".format(len(items)))
            self.redox.update(docs=items, key=[self.website.key])
        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indicies on the redox and molecules collections
        """
        # Search index for molecules
        self.molecules.ensure_index(self.molecules.key, unique=True)
        self.molecules.ensure_index(self.molecules.lu_field)
        self.molecules.ensure_index("formula_alphabetical")
        
        # Search index for molecules
        self.redox.ensure_index(self.redox.key, unique=True)
        self.redox.ensure_index(self.redox.lu_field)
        self.redox.ensure_index("formula_alphabetical")

        # Search index for website
        self.website.ensure_index(self.redox.key, unique=True)
        self.website.ensure_index(self.redox.lu_field)
        self.website.ensure_index("formula_alphabetical")

    

