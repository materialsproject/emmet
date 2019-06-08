import os
import shlex
import subprocess
import re
from datetime import datetime
from itertools import chain, groupby
import numpy as np
import networkx as nx

from pymatgen import Molecule
from pymatgen.analysis.graphs import MoleculeGraph, isomorphic
from pymatgen.analysis.local_env import OpenBabelNN
from pymatgen.io.babel import BabelMolAdaptor
from pymatgen.io.xyz import XYZ
from pymatgen.symmetry.analyzer import PointGroupAnalyzer

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

        # Save timestamp for update operation
        self.timestamp = datetime.utcnow()

        redox_task_ids = self.redox.distinct(self.redox.key, {"$or":[{"redox.IE":{"$exists":1}}, {"redox.EA":{"$exists":1}}]})

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

        doc = {}

        self.logger.debug(
            f"Procesing an entry with fomula {item['formula_alphabetical']}"
        )
        mol = Molecule.from_dict(item["molecule"])
        doc["_id"] = item["_id"]
        doc["run_tags"] = {"methods": [item["basis"],item["method"]]}
        doc["charge"] = item["charge"]
        doc["spin_multiplicity"] = mol.spin_multiplicity
        doc["electrode_potentials"] = {}
        if "EA" in item["redox"]:
            if "solvated" in item["redox"]["EA"]:
                doc["EA"] = item["redox"]["EA"]["solvated"]
                doc["electrode_potentials"]["reduction"] = {}
                doc["electrode_potentials"]["reduction"]["lithium"] = item["redox"]["reduction"]["solvated"]["Li"]
                doc["electrode_potentials"]["reduction"]["hydrogen"] = item["redox"]["reduction"]["solvated"]["H"]
                doc["electrode_potentials"]["reduction"]["magnesium"] = item["redox"]["reduction"]["solvated"]["Mg"]
            elif "vacuum" in item["redox"]["EA"]:
                doc["EA"] = item["redox"]["EA"]["vacuum"]
                doc["electrode_potentials"]["reduction"] = {}
                doc["electrode_potentials"]["reduction"]["lithium"] = item["redox"]["reduction"]["vacuum"]["Li"]
                doc["electrode_potentials"]["reduction"]["hydrogen"] = item["redox"]["reduction"]["vacuum"]["H"]
                doc["electrode_potentials"]["reduction"]["magnesium"] = item["redox"]["reduction"]["vacuum"]["Mg"]
        if "IE" in item["redox"]:
            if "solvated" in item["redox"]["IE"]:
                doc["IE"] = item["redox"]["IE"]["solvated"]
                doc["electrode_potentials"]["oxidation"] = {}
                doc["electrode_potentials"]["oxidation"]["lithium"] = item["redox"]["oxidation"]["solvated"]["Li"]
                doc["electrode_potentials"]["oxidation"]["hydrogen"] = item["redox"]["oxidation"]["solvated"]["H"]
                doc["electrode_potentials"]["oxidation"]["magnesium"] = item["redox"]["oxidation"]["solvated"]["Mg"]
            elif "vacuum" in item["redox"]["IE"]:
                doc["IE"] = item["redox"]["IE"]["vacuum"]
                doc["electrode_potentials"]["oxidation"] = {}
                doc["electrode_potentials"]["oxidation"]["lithium"] = item["redox"]["oxidation"]["vacuum"]["Li"]
                doc["electrode_potentials"]["oxidation"]["hydrogen"] = item["redox"]["oxidation"]["vacuum"]["H"]
                doc["electrode_potentials"]["oxidation"]["magnesium"] = item["redox"]["oxidation"]["vacuum"]["Mg"]
        if "EA" in item["redox"] and "IE" in item["redox"]:
            if "solvated" in item["redox"]["EA"]:
                doc["electrochemical_window_width"] = item["redox"]["EA"]["solvated"] - item["redox"]["IE"]["solvated"]
            elif "vacuum" in item["redox"]["EA"]:
                doc["electrochemical_window_width"] = item["redox"]["EA"]["vacuum"] - item["redox"]["IE"]["vacuum"]
        doc["molecule"] = item["molecule"]

        bb = BabelMolAdaptor(mol)
        pbmol = bb.pybel_mol
        doc["xyz"] = XYZ(mol)
        doc["smiles"] = pbmol.write(str("smi")).split()[0]
        doc["can"] = pbmol.write(str("can")).split()[0]
        doc["inchi"] = pbmol.write(str("inchi")).strip()
        doc["inchi_root"] = pbmol.write(str("inchi")).strip()
        doc["svg"] = modify_svg(xyz2svg(doc["xyz"]))

        pga = PointGroupAnalyzer(mol)
        doc["pointgroup"] = pga.sch_symbol
        comp = mol.composition
        doc["elements"] = list(comp.as_dict().keys())
        doc["nelements"] = len(comp)
        doc["formula"] = comp.formula
        doc["pretty_formula"] = comp.reduced_formula
        doc["reduced_cell_formula_abc"] = comp.alphabetical_formula
        doc["MW"] = comp.weight
        doc["user_tags"] = {}

        # This is true for all calculations that this builder will be used for:
        doc["implicit_solvent"] = {
            "solvent_probe_radius" : 0.0,
            "vdwscale" : 1.1,
            "solvent_name" : "water",
            "radii" : "uff",
            "dielectric_constant" : 78.3553,
            "model" : "ief-pcm_at_surface0.00"
        }

        # WARNING: this task ID will likely clash with one already present in the database!
        doc["task_id_deprecated"] = "task_id"
        doc["task_id"] = "mol-"+str(item["task_id"])

        # Don't have time to deal with the SNL right now, and the data all seems redundant,
        # so I'm hoping the webside doesn't use it.
        doc["snl_final"] = None
        doc["snlgroup_id_final"] = None

        # Directly copied from the website doc I have:
        doc["sbxn"] = ["core","jcesr","vw"]

        return doc

    def update_targets(self, items):
        """
        Inserts the redox docs into the redox collection

        Args:
            items ([dict]): a list of lists of redox dictionaries to update
        """
        # print(self.website.key)
        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info("Updating {} website documents".format(len(items)))
            self.website.update(docs=items, key=[self.website.key])
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
        self.website.ensure_index(self.website.key, unique=True)
        self.website.ensure_index(self.website.lu_field)
        self.website.ensure_index("formula_alphabetical")


# The two functions below were taken directly from Rubicon
def xyz2svg(xyz):
    babel_cmd = shlex.split("babel -ixyz -osvg")
    p = subprocess.Popen(babel_cmd,
                         stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate(str(xyz).encode('utf-8'))
    return str(out)


def modify_svg(svg):
    """
    Hack to the svg code to enhance the molecule.
    Because Xiaohui have no aeshetic cell, please change it a more
    beautiful color scheme
    """
    tokens = svg.split('\n')
    new_tokens = []
    for line in tokens:
        if "line" in line:
            line = re.sub('stroke-width="\d+.?\d*"',
                          'stroke-width="3.0"', line)
        if "rect" in line:
            line = re.sub(r'fill=".+?"', 'fill="Beige"', line)
        if ">H</text>" in line:
            line = re.sub(r'fill=".+?"', 'fill="DimGray"', line)
            line = re.sub(r'stroke=".+?"', 'stroke="DimGray"', line)
        new_tokens.append(line)
    new_svg = '\n'.join(new_tokens)
    return new_svg
