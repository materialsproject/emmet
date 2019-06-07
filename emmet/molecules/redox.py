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

REDOX_REFS = {"Li": 4.4-3.0, "H": 4.4, "Mg": 4.4-2.4}

class RedoxBuilder(Builder):
    def __init__(self,
                 molecules,
                 redox,
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
        self.query = query if query else {}
        super().__init__(sources=[molecules], targets=[redox], **kwargs)

    def get_items(self):
        """
        Gets sets of entries from formula_alphabetical that need to be processed

        Returns:
            generator of relevant entries from one formula_alphabetical
        """

        self.logger.info("Redox builder started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp for update operation
        self.timestamp = datetime.utcnow()

        # All relevant molecules that have been updated since redox props were
        # last calculated
        q = dict(self.query)
        q.update(self.molecules.lu_filter(self.redox))
        updated_forms = set(self.molecules.distinct("formula_alphabetical", q))

        # All molecules that are not present in the redox collection
        redox_mol_ids = self.redox.distinct(self.redox.key)
        q = dict(self.query)
        q.update({self.molecules.key: {"$nin": redox_mol_ids}})
        new_mol_forms = set(self.molecules.distinct("formula_alphabetical", q))

        # All formula_alphabetical not present in redox collection
        new_forms = set(self.molecules.distinct("formula_alphabetical", self.query)) - set(
            self.redox.distinct("formula_alphabetical")
        )

        forms = updated_forms | new_forms | new_mol_forms

        self.logger.info(
            "Found {} formulae with new/updated molecules".format(len(forms))
        )
        self.total = len(forms)

        for formula_alphabetical in forms:
            yield self.get_entries(formula_alphabetical)

    def process_item(self, item):
        """
        Process the list of entries into redox docs

        Args:
            item (set(entry)): a list of entries to process into a redox doc

        Returns:
            [dict]: a list of redox dictionaries to update redox with
        """

        docs = []

        self.logger.debug(
            f"Procesing {len(item)} entries for {item[0]['formula_alphabetical']}"
        )

        grouped_molecules = group_molecules_and_sort_by_charge(item)

        for group in grouped_molecules:
            group_docs = []
            # Calculating the Gibbs free energy of each molecule
            for mol in group:
                doc = {
                    self.redox.key: mol[self.molecules.key],
                    "charge": mol["molecule"]["charge"],
                    "last_updated": mol["last_updated"],
                    "formula_alphabetical": mol["formula_alphabetical"],
                    "gibbs": {}
                }
                required_vals = ["vacuum_energy","vacuum_enthalpy","vacuum_entropy","solvated_energy","solvated_enthalpy","solvated_entropy"]
                missing_keys = [k for k in required_vals if k not in mol]
                if len(missing_keys) > 0:
                    doc["_warnings"] = ["missing energy keys: {}".format(missing_keys)]
                if "vacuum_energy" in mol:
                    doc["gibbs"]["vacuum"] = mol["vacuum_energy"]*27.21139+0.0433641*mol.get("vacuum_enthalpy",0.0)-298*mol.get("vacuum_entropy",0.0)*0.0000433641
                if "solvated_energy" in mol:
                    doc["gibbs"]["solvated"] = mol["solvated_energy"]*27.21139+0.0433641*mol.get("solvated_enthalpy",0.0)-298*mol.get("solvated_entropy",0.0)*0.0000433641
                group_docs.append(doc)
            # Calculating ionization energy and electron affinity if multiple charges present
            if len(group_docs) > 1:
                for ii,doc in enumerate(group_docs):
                    redox = {}
                    if ii != len(group_docs)-1:
                        if abs(doc["charge"]-group_docs[ii+1]["charge"]) == 1:
                            redox["IE"] = {}
                            for key in doc["gibbs"]:
                                if key in group_docs[ii+1]["gibbs"]:
                                    redox["IE"][key] = group_docs[ii+1]["gibbs"][key] - doc["gibbs"][key]
                            # Calculating oxidation potentials if IE present
                            oxidation = {}
                            for key in redox["IE"]:
                                oxidation[key] = {}
                                for ref_key in REDOX_REFS:
                                    oxidation[key][ref_key] = redox["IE"][key]-REDOX_REFS[ref_key]
                            redox["oxidation"] = oxidation
                    if ii != 0:
                        if abs(doc["charge"]-group_docs[ii-1]["charge"]) == 1:
                            redox["EA"] = {}
                            for key in doc["gibbs"]:
                                if key in group_docs[ii-1]["gibbs"]:
                                    redox["EA"][key] = doc["gibbs"][key] - group_docs[ii-1]["gibbs"][key]
                            # Calculating reduction potentials if IE present
                            reduction = {}
                            for key in redox["EA"]:
                                reduction[key] = {}
                                for ref_key in REDOX_REFS:
                                    reduction[key][ref_key] = redox["EA"][key]-REDOX_REFS[ref_key]
                            redox["reduction"] = reduction
                    doc["redox"] = redox

            docs.extend(group_docs)

        return docs

    def update_targets(self, items):
        """
        Inserts the redox docs into the redox collection

        Args:
            items ([[dict]]): a list of lists of redox dictionaries to update
        """
        # flatten out lists
        items = list(filter(None, chain.from_iterable(items)))

        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info("Updating {} redox documents".format(len(items)))
            self.redox.update(docs=items, key=[self.redox.key])
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

    def get_entries(self, formula_alphabetical):
        """
        Get all entries with a formula_alphabetical from molecules

        Args:
            formula_alphabetical(str): an alphabetized formula

        Returns:
            a set of entries for this system
        """

        self.logger.info("Getting entries for: {}".format(formula_alphabetical))
        new_q = dict(self.query)
        new_q["formula_alphabetical"] = formula_alphabetical
        new_q["deprecated"] = False

        fields = [
            "molecule",
            "vacuum_molecule",
            "solvated_molecule",
            self.molecules.key,
            "energy",
            "vacuum_energy",
            "solvated_energy",
            "enthalpy",
            "vacuum_enthalpy",
            "solvated_enthalpy",
            "entropy",
            "vacuum_entropy",
            "solvated_entropy",
            "formula_alphabetical",
            "last_updated"
        ]
        all_entries = list(self.molecules.query(properties=fields, criteria=new_q))

        self.logger.info("Total entries in {} : {}".format(formula_alphabetical, len(all_entries)))

        return all_entries


def group_molecules_and_sort_by_charge(molecules):
    """
    Groups molecules that all have the same formula according to connectivity,
    # then sorts each group by molecular charge.
    """
    groups = []
    for mol_dict in molecules:
        mol = Molecule.from_dict(mol_dict["molecule"])
        mol_graph = MoleculeGraph.with_local_env_strategy(mol,
                                                          OpenBabelNN(),
                                                          reorder=False,
                                                          extend_structure=False)
        if nx.is_connected(mol_graph.graph.to_undirected()):
            matched = False
            for group in groups:
                if isomorphic(mol_graph.graph,group["mol_graph"].graph,True):
                    group["mol_dict_list"].append(mol_dict)
                    matched = True
                    break
            if not matched:
                groups.append({"mol_graph":mol_graph,"mol_dict_list":[mol_dict]})
    for group in groups:
        yield sorted(group["mol_dict_list"], key=lambda mol: mol["molecule"]["charge"])
