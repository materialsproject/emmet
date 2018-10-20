from datetime import datetime
import os
import os.path
import string
import traceback
import copy
import nltk
import numpy as np
from ast import literal_eval
from itertools import groupby

from monty.json import jsanitize
from monty.serialization import loadfn

from maggma.examples.builders import Builder, get_keys
from maggma.utils import grouper
from maggma.validator import JSONSchemaValidator, msonable_schema
from pydash.objects import get, set_, has

from emmet.materials.snls import mp_default_snl_fields
from emmet.common.utils import scrub_class_and_module
from emmet import __version__ as emmet_version

# Import for crazy things this builder needs
from pymatgen.io.cif import CifWriter
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen import Structure
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.analysis.structure_analyzer import RelaxationAnalyzer
from pymatgen.analysis.diffraction.core import DiffractionPattern
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer
from pymatgen.util.provenance import StructureNL
from pymatgen import __version__ as pymatgen_version

from mp_dash_components.converters.structure import StructureIntermediateFormat
from mp_dash_components import __version__ as mp_dash_components_version

# Silly fix to keep pybtex from spamming warnings
import os, pybtex
devnull = open(os.devnull, 'w')
pybtex.io.stderr = devnull

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
MPBUILDER_SCHEMA = os.path.join(MODULE_DIR, "schema", "mp_website.json")
MPBUILDER_SETTINGS = os.path.join(MODULE_DIR, "settings", "mp_website.json")

latt_para_interval = [1.50 - 1.96 * 3.14, 1.50 + 1.96 * 3.14]
vol_interval = [4.56 - 1.96 * 7.82, 4.56 + 1.96 * 7.82]


class MPBuilder(Builder):
    def __init__(self, materials, website, aux=None, query=None, **kwargs):
        """
        Creates a MP Website style materials doc.
        This builder is a bit unweildy as MP will eventually move to a new format
        written for backwards compatability with previous infrastructure

        Args:
            tasks (Store): Store of task documents
            materials (Store): Store of materials documents - 
                should be aggregate across multiple stores using JointStore
            website (Store): Store of the mp style website docs
            aux ([Store]): Auxillary data collection to join to materials doc
                for processing
        """
        self.materials = materials
        self.website = website
        self.aux = aux if aux else []
        self.query = query
        #        self.website.validator = JSONSchemaValidator(MPBUILDER_SCHEMA)
        self._settings = loadfn(MPBUILDER_SETTINGS)

        super().__init__(sources=[materials] + aux, targets=[website], **kwargs)

    def calc(self, item):

        mat = old_style_mat(item)

        # These functions convert data from old style to new style
        add_es(mat, item)
        add_xrd(mat, item)
        add_elastic(mat, item)
        add_bonds(mat, item)
        add_propnet(mat, item)
        add_snl(mat, item)
        check_relaxation(mat, new_style_mat)
        add_cifs(mat)
        add_viewer_json(mat)
        add_meta(mat)
        sandbox_props(mat)
        has_fields(mat)

        return jsanitize(mat)

    def old_style_mat(self, new_style_mat):
        """
        Creates the base document for the old MP mapidoc style from the new document structure
        """

        mat = {}
        mp_conversion_dict = self._settings["conversion_dict"]
        mag_types = self._settings["mag_types"]

        # Uses the conversion dict to copy over values which handles the bulk of the work.
        for mp, new_key in mp_conversion_dict.items():
            if has(new_style_mat, new_key):
                set_(mat, mp, get(new_style_mat, new_key))

        struc = Structure.from_dict(mat["structure"])
        mat["is_ordered"] = True
        mat["is_compatible"] = True
        mat["oxide_type"] = oxide_type(struc)
        mat["reduced_cell_formula"] = struc.composition.reduced_composition.as_dict()
        mat["unit_cell_formula"] = struc.composition.as_dict()
        mat["full_formula"] = "".join(struc.formula.split())
        vals = sorted(mat["reduced_cell_formula"].values())
        mat["anonymous_formula"] = {string.ascii_uppercase[i]: float(vals[i]) for i in range(len(vals))}
        mat["initial_structure"] = new_style_mat.get("initial_structure", None)
        mat["nsites"] = struc.get_primitive_structure().num_sites
        mat["magnetic_type"] = mag_types.get(mat.get("magnetic_type", None), "Unknown")

        set_(mat, "pseudo_potential.functional", "PBE")

        set_(mat, "pseudo_potential.labels",
             [p["titel"].split()[1] for p in get(new_style_mat, "calc_settings.potcar_spec")])
        set_(mat, "pseudo_potential.pot_type", "paw")

        mat["ntask_ids"] = len(get(new_style_mat, "task_ids"))
        mat["blessed_tasks"] = {v: k for k, v in new_style_mat.get("task_types", {}).items()}

        return mat

    def sandbox_props(self, mat):
        sandbox_props = self._settings["sandboxed_properties"]
        mat["sbxn"] = mat.get("sbxn", ["core", "jcesr", "vw", "shyamd", "kitchaev"])
        mat["sbxd"] = []

        for sbx in mat["sbxn"]:
            sbx_d = {k: get(mat, v) for k, v in sandbox_props.items() if has(mat, k)}
            sbx_d["id"] = sbx
            mat["sbxd"].append(sbx_d)


#
#
#
#
# THIS SECTION DEFINES EXTRA FUNCTIONS THAT MODIFY THE MAT DOC PER MP DOC STRUCTURE
#
#


def add_es(mat, new_style_mat):

    bs_origin = None
    dos_origin = None
    try:
        bs_origin = next((origin for origin in new_style_mat.get("origins", []) if "Line" in origin["task_type"]), None)
        dos_origin = next((origin for origin in new_style_mat.get("origins", []) if "Uniform" in origin["task_type"]),
                          None)

        if bs_origin:
            u_type = "GGA+U" if "+U" in bs_origin["task_type"] else "GGA"
            set_(mat, "band_structure.{}.task_id".format(u_type), bs_origin["task_id"])

        if dos_origin:
            u_type = "GGA+U" if "+U" in dos_origin["task_type"] else "GGA"
            set_(mat, "dos.{}.task_id".format(u_type), dos_origin["task_id"])

    except Exception as e:
        print("Error in adding electronic structure: {}".format(e))

    mat["has_bandstructure"] = bool(bs_origin) and bool(dos_origin)


def add_elastic(mat, new_style_mat):
    if "elasticity" in new_style_mat:
        mat["elasticity"] = {k: elastic["elasticity"].get(v, None) for k, v in es_aliases.items()}
        if has(elastic, "elasticity.structure.sites"):
            mat["elasticity"]["nsites"] = len(get(elastic, "elasticity.structure.sites"))
        else:
            mat["elasticity"]["nsites"] = len(get(mat, "structure.sites"))


def add_cifs(doc):
    symprec = 0.1
    struc = Structure.from_dict(doc["structure"])
    sym_finder = SpacegroupAnalyzer(struc, symprec=symprec)
    doc["cif"] = str(CifWriter(struc))
    doc["cifs"] = {}
    if sym_finder.get_hall():
        primitive = sym_finder.get_primitive_standard_structure()
        conventional = sym_finder.get_conventional_standard_structure()
        refined = sym_finder.get_refined_structure()
        doc["cifs"]["primitive"] = str(CifWriter(primitive))
        doc["cifs"]["refined"] = str(CifWriter(refined, symprec=symprec))
        doc["cifs"]["conventional_standard"] = str(CifWriter(conventional, symprec=symprec))
        doc["cifs"]["computed"] = str(CifWriter(struc, symprec=symprec))
        doc["spacegroup"]["symbol"] = sym_finder.get_space_group_symbol()
        doc["spacegroup"]["number"] = sym_finder.get_space_group_number()
        doc["spacegroup"]["point_group"] = sym_finder.get_point_group_symbol()
        doc["spacegroup"]["crystal_system"] = sym_finder.get_crystal_system()
        doc["spacegroup"]["hall"] = sym_finder.get_hall()
    else:
        doc["cifs"]["primitive"] = None
        doc["cifs"]["refined"] = None
        doc["cifs"]["conventional_standard"] = None


def add_xrd(mat, new_style_mat):
    mat["xrd"] = {}
    for el, doc in new_style_mat["xrd"].items():
        el_doc = {}
        el_doc["meta"] = ["amplitude", "hkl", "two_theta", "d_spacing"]
        el_doc["created_at"] = datetime.now().isoformat()
        el_doc["wavelength"] = doc["wavelength"]

        xrd_pattern = DiffractionPattern.from_dict(doc["pattern"])
        el_doc["pattern"] = [[
            float(intensity), [int(x) for x in literal_eval(list(hkls.keys())[0])], two_theta,
            float(d_hkl)
        ] for two_theta, intensity, hkls, d_hkl in zip(xrd_pattern.x, xrd_pattern.y, xrd_pattern.hkls, xrd_pattern.
                                                       d_hkls)]

        mat["xrd"][el] = el_doc


def add_bonds(mat, bonds):
    if bonds.get('successful', False):
        mat["bonds"] = bonds["summary"]


def add_snl(mat, snl=None):
    mat["snl"] = copy.deepcopy(mat["structure"])
    if snl:
        mat["snl"].update(snl["snl"])
    else:
        mat["snl"] = StructureNL(Structure.from_dict(mat["structure"]), []).as_dict()
        mat["snl"]["about"].update(mp_default_snl_fields)

    mat["snl_final"] = mat["snl"]
    mat["icsd_ids"] = [int(i) for i in get(mat["snl"], "about._db_ids.icsd_ids", [])]
    mat["pf_ids"] = get(mat["snl"], "about._db_ids.pf_ids", [])

    # Extract tags from remarks by looking for just nounds and adjectives
    mat["exp"] = {"tags": []}
    for remark in mat["snl"]["about"].get("_tags", []):
        tokens = set(tok[1] for tok in nltk.pos_tag(nltk.word_tokenize(remark), tagset='universal'))
        if len(tokens.intersection({"ADV", "ADP", "VERB"})) == 0:
            mat["exp"]["tags"].append(remark)


def add_propnet(mat, propnet):
    exclude_list = ['compliance_tensor_voigt', 'task_id', '_id', 'pretty_formula', 'inputs', 'last_updated']
    for e in exclude_list:
        if e in propnet:
            del propnet[e]
    mat["propnet"] = scrub_class_and_module(propnet)


def check_relaxation(mat, new_style_mat):
    final_structure = Structure.from_dict(mat["structure"])

    warnings = []
    # Check relaxation for just the initial structure to optimized structure
    init_struc = new_style_mat["initial_structure"]

    orig_crystal = Structure.from_dict(init_struc)

    try:
        analyzer = RelaxationAnalyzer(orig_crystal, final_structure)
        latt_para_percentage_changes = analyzer.get_percentage_lattice_parameter_changes()
        for l in ["a", "b", "c"]:
            change = latt_para_percentage_changes[l] * 100
            if change < latt_para_interval[0] or change > latt_para_interval[1]:
                warnings.append("Large change in a lattice parameter during relaxation.")
        change = analyzer.get_percentage_volume_change() * 100
        if change < vol_interval[0] or change > vol_interval[1]:
            warnings.append("Large change in volume during relaxation.")
    except Exception as ex:
        # print icsd_crystal.formula
        # print final_structure.formula
        print("Relaxation analyzer failed for Material:{} due to {}".format(mat["task_id"], traceback.print_exc()))

    mat["warnings"] = list(set(warnings))


def add_viewer_json(mat):
    """
    Generate JSON for structure viewer.
    """
    structure = Structure.from_dict(mat['structure'])
    canonical_json = StructureIntermediateFormat(structure).json
    sga = SpacegroupAnalyzer(structure, symprec=0.1)
    conventional_structure = sga.get_conventional_standard_structure()
    conventional_json = StructureIntermediateFormat(conventional_structure).json
    mat["_viewer"] = {
        "structure_json": canonical_json,
        "conventional_structure_json": conventional_json,
        "_mp_dash_components_version": mp_dash_components_version
    }


def has_fields(mat):
    mat["has"] = [prop for prop in ["elasticity", "piezo", "diel"] if prop in mat]
    if "band_structure" in mat:
        mat["has"].append("bandstructure")


def add_meta(mat):
    meta = {'emmet_version': emmet_version, 'pymatgen_version': pymatgen_version}
    mat['_meta'] = meta
