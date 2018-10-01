from datetime import datetime
import os
import string
import traceback
import copy
import nltk
import numpy as np
from ast import literal_eval

from monty.json import jsanitize

from maggma.builder import Builder
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

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))

mp_conversion_dict = {
    "anonymous_formula": "formula_anonymous",
    "band_gap.search_gap.band_gap": "bandstructure.band_gap",
    "band_gap.search_gap.is_direct": "bandstructure.is_gap_direct",
    "chemsys": "chemsys",
    "delta_volume": "analysis.delta_volume",
    "density": "density",
    "efermi": "bandstructure.efermi",
    "elements": "elements",
    "final_energy": "thermo.energy",
    "final_energy_per_atom": "thermo.energy_per_atom",
    "hubbards": "calc_settings.hubbards",
    "initial_structure": "initial_structure",
    "input.crystal": "initial_structure",
    "input.potcar_spec": "calc_settings.potcar_spec",
    "is_hubbard": "calc_settings.is_hubbard",
    "nelements": "nelements",
    "nsites": "nsites",
    "pretty_formula": "formula_pretty",
    "reduced_cell_formula": "composition_reduced",
    "run_type": "calc_settings.run_type",
    "spacegroup": "spacegroup",
    "structure": "structure",
    "total_magnetization": "magnetism.total_magnetization",
    "unit_cell_formula": "composition",
    "volume": "volume",
    "warnings": "analysis.warnings",
    "task_ids": "task_ids",
    "task_id": "task_id",
    "original_task_id": "task_id",
    "input.incar": "inputs.structure_optimization.incar",
    "input.kpoints": "inputs.structure_optimization.kpoints",
    "encut": "inputs.structure_optimization.incar.ENCUT",
    "formula_anonymous": "formula_anonymous"
}

SANDBOXED_PROPERTIES = {"e_above_hull": "e_above_hull", "decomposes_to": "decomposes_to"}

mag_types = {"NM": "Non-magnetic", "FiM": "Ferri", "AFM": "AFM", "FM": "FM"}

latt_para_interval = [1.50 - 1.96 * 3.14, 1.50 + 1.96 * 3.14]
vol_interval = [4.56 - 1.96 * 7.82, 4.56 + 1.96 * 7.82]


# minimal schema for now
MPBUILDER_SCHEMA = {
    "title": "mp_materials",
    "type": "object",
    "properties":
        {
            "task_id": {"type": "string"},
            "e_above_hull": {"type": "number", "minimum": 0},
            "structure": msonable_schema(Structure)
        },
    "required": ["task_id", "e_above_hull", "structure"]
}


class MPBuilder(Builder):
    def __init__(self,
                 materials,
                 mp_materials,
                 thermo=None,
                 electronic_structure=None,
                 snls=None,
                 xrd=None,
                 elastic=None,
                 dielectric=None,
                 dois=None,
                 magnetism=None,
                 bond_valence=None,
                 bonds=None,
                 propnet=None,
                 query=None,
                 **kwargs):
        """
        Creates a MP Website style materials doc.
        This builder is a bit unweildy as MP will eventually move to a new format
        Written for backwards compatability with previous infrastructure

        Args:
            tasks (Store): Store of task documents
            materials (Store): Store of materials documents
            mp_web (Store): Store of the mp style website docs, This will also make an electronic_structure collection and an es_plot gridfs
        """
        self.materials = materials
        self.mp_materials = mp_materials
        self.electronic_structure = electronic_structure
        self.snls = snls
        self.thermo = thermo
        self.query = query if query else {}
        self.xrd = xrd
        self.elastic = elastic
        self.dielectric = dielectric
        self.dois = dois
        self.magnetism = magnetism
        self.bond_valence = bond_valence
        self.bonds = bonds
        self.propnet = propnet

        self.mp_materials.validator = JSONSchemaValidator(MPBUILDER_SCHEMA)

        sources = list(
            filter(None, [materials, thermo, electronic_structure, snls,
                          elastic, dielectric, xrd, dois, magnetism,
                          bond_valence, propnet]))

        super().__init__(sources=sources, targets=[mp_materials], **kwargs)

    def get_items(self):
        """
        Gets all materials that need a new MP Style materials document

        Returns:
            generator of materials to calculate xrd
        """

        self.logger.info("MP Website Builder Started")

        self.ensure_indicies()

        # Get all new materials
        q = dict(self.query)
        new_mats = set(self.materials.distinct(self.materials.key)) - set(
            self.mp_materials.distinct(self.mp_materials.key, q))

        self.logger.info("Found {} new materials for the website".format(len(new_mats)))

        # All relevant materials that have been updated since MP Website Materials
        # were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.mp_materials))
        mats = set(self.materials.distinct(self.materials.key, q))

        self.logger.info("Found {} updated materials for the website".format(len(mats)))

        mats = mats | new_mats
        self.logger.info("Processing {} total materials".format(len(mats)))
        self.total = len(mats)

        for m in mats:

            doc = {"material": self.materials.query_one(criteria={self.materials.key: m})}

            if self.electronic_structure:
                doc["electronic_structure"] = self.electronic_structure.query_one(criteria={
                    self.electronic_structure.key: m,
                    "band_gap": {
                        "$exists": 1
                    }
                })

            if self.elastic:
                doc["elastic"] = self.elastic.query_one(criteria={self.elastic.key: m})

            if self.dielectric:
                doc["dielectric"] = self.dielectric.query_one(criteria={self.dielectric.key: m})

            if self.thermo:
                doc["thermo"] = self.thermo.query_one(criteria={self.thermo.key: m})

            if self.snls:
                doc["snl"] = self.snls.query_one(criteria={self.snls.key: m})

            if self.xrd:
                doc["xrd"] = self.xrd.query_one(criteria={self.xrd.key: m})

            if self.dois:
                doc["dois"] = self.dois.query_one(criteria={self.dois.key: m})

            if self.magnetism:
                doc['magnetism'] = self.magnetism.query_one(criteria={self.magnetism.key: m})

            if self.bond_valence:
                doc['bond_valence'] = self.bond_valence.query_one(criteria={self.bond_valence.key: m})

            if self.bonds:
                doc['bonds'] = self.bonds.query_one(criteria={self.bonds.key: m, "strategy": "CrystalNN"})

            if self.propnet:
                doc['propnet'] = self.propnet.query_one(
                    criteria={self.propnet.key: m})

            yield doc

    def process_item(self, item):

        new_style_mat = item["material"]

        mat = old_style_mat(new_style_mat)
        add_es(mat, new_style_mat)

        if item.get("xrd", None):
            xrd = item["xrd"]
            add_xrd(mat, xrd)

        if item.get("dielectric", None):
            dielectric = item["dielectric"]
            add_dielectric(mat, dielectric)

        if item.get("elastic", None):
            elastic = item["elastic"]
            add_elastic(mat, elastic)

        if item.get("thermo", None):
            thermo = item["thermo"]
            add_thermo(mat, thermo)

        if item.get("dois", None):
            doi = item["dois"]
            add_dois(mat, doi)

        if item.get("bond_valence", None):
            bond_valence = item["bond_valence"]
            add_bond_valence(mat, bond_valence)

        if item.get("bonds", None):
            bonds = item["bonds"]
            add_bonds(mat, bonds)

        if item.get("propnet", None):
            propnet = item["propnet"]
            add_propnet(mat, propnet)

        snl = item.get("snl", {})
        add_snl(mat, snl)
        add_magnetism(mat, item.get("magnetism", None))
        add_viewer_json(mat)
        add_meta(mat)
        sandbox_props(mat)
        has_fields(mat)
        return jsanitize(mat)

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([[dict]]): a list of list of thermo dictionaries to update
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} mp materials docs".format(len(items)))
            self.mp_materials.update(docs=items, ordered=False)
        else:
            self.logger.info("No items to update")

    def ensure_indicies(self):
        """
        Ensures indexes on the tasks and materials collections
        :return:
        """

        # Search index for materials
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index("task_ids")


#
#
#
#
# THIS SECTION DEFINES EXTRA FUNCTIONS THAT MODIFY THE MAT DOC PER MP DOC STRUCTURE
#
#


def old_style_mat(new_style_mat):
    """
    Creates the base document for the old MP mapidoc style from the new document structure
    """

    mat = {}
    for mp, new_key in mp_conversion_dict.items():
        if has(new_style_mat, new_key):
            set_(mat, mp, get(new_style_mat, new_key))

    mat["is_ordered"] = True
    mat["is_compatible"] = True

    struc = Structure.from_dict(mat["structure"])
    mat["oxide_type"] = oxide_type(struc)
    mat["reduced_cell_formula"] = struc.composition.reduced_composition.as_dict()
    mat["unit_cell_formula"] = struc.composition.as_dict()
    mat["full_formula"] = "".join(struc.formula.split())
    vals = sorted(mat["reduced_cell_formula"].values())
    mat["anonymous_formula"] = {string.ascii_uppercase[i]: float(vals[i]) for i in range(len(vals))}
    mat["initial_structure"] = new_style_mat.get("initial_structure", None)
    mat["nsites"] = struc.get_primitive_structure().num_sites


    set_(mat, "pseudo_potential.functional", "PBE")

    set_(mat, "pseudo_potential.labels",
         [p["titel"].split()[1] for p in get(new_style_mat, "calc_settings.potcar_spec")])
    mat["ntask_ids"] = len(get(new_style_mat, "task_ids"))
    set_(mat, "pseudo_potential.pot_type", "paw")
    add_blessed_tasks(mat, new_style_mat)
    add_cifs(mat)
    check_relaxation(mat, new_style_mat)

    return mat


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


def add_blessed_tasks(mat, new_style_mat):
    blessed_tasks = {}
    for doc in new_style_mat["origins"]:
        blessed_tasks[doc["task_type"]] = doc["task_id"]

    mat["blessed_tasks"] = blessed_tasks


def add_elastic(mat, elastic):
    es_aliases = {
        "G_Reuss": "g_reuss",
        "G_VRH": "g_vrh",
        "G_Voigt": "g_voigt",
        "G_Voigt_Reuss_Hill": "g_vrh",
        "K_Reuss": "k_reuss",
        "K_VRH": "k_vrh",
        "K_Voigt": "k_voigt",
        "K_Voigt_Reuss_Hill": "k_vrh",
        #        "calculations": "calculations",    <--- TODO: Add to elastic builder?
        "elastic_anisotropy": "universal_anisotropy",
        "elastic_tensor": "elastic_tensor",
        "homogeneous_poisson": "homogeneous_poisson",
        "poisson_ratio": "homogeneous_poisson",
        "universal_anisotropy": "universal_anisotropy",
        "elastic_tensor_original": "elastic_tensor_original",
        "compliance_tensor": "compliance_tensor",
        "third_order": "third_order"
    }

    mat["elasticity"] = {k: elastic["elasticity"].get(v, None)
                         for k, v in es_aliases.items()}
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
        doc["cifs"]["conventional_standard"] = str(CifWriter(conventional))
        doc["cifs"]["computed"] = str(CifWriter(struc))
        doc["spacegroup"]["symbol"] = sym_finder.get_space_group_symbol()
        doc["spacegroup"]["number"] = sym_finder.get_space_group_number()
        doc["spacegroup"]["point_group"] = sym_finder.get_point_group_symbol()
        doc["spacegroup"]["crystal_system"] = sym_finder.get_crystal_system()
        doc["spacegroup"]["hall"] = sym_finder.get_hall()
    else:
        doc["cifs"]["primitive"] = None
        doc["cifs"]["refined"] = None
        doc["cifs"]["conventional_standard"] = None


def add_xrd(mat, xrd):
    mat["xrd"] = {}
    for el, doc in xrd["xrd"].items():
        el_doc = {}
        el_doc["meta"] = ["amplitude", "hkl", "two_theta", "d_spacing"]
        el_doc["created_at"] = datetime.now().isoformat()
        el_doc["wavelength"] = doc["wavelength"]

        xrd_pattern = DiffractionPattern.from_dict(doc["pattern"])
        el_doc["pattern"] = [[
            float(intensity), [int(x) for x in literal_eval(list(hkls.keys())[0])], two_theta,
            float(d_hkl)
        ] for two_theta, intensity, hkls, d_hkl in zip(xrd_pattern.x, xrd_pattern.y, xrd_pattern.hkls,
                                                       xrd_pattern.d_hkls)]

        mat["xrd"][el] = el_doc


def add_thermo(mat, thermo):
    if has(thermo, "thermo.e_above_hull"):
        set_(mat, "e_above_hull", get(thermo, "thermo.e_above_hull"))

    if has(thermo, "thermo.formation_energy_per_atom"):
        set_(mat, "formation_energy_per_atom", get(thermo, "thermo.formation_energy_per_atom"))

    if has(thermo, "thermo.decomposes_to"):
        set_(mat, "decomposes_to", get(thermo, "thermo.decomposes_to"))


def sandbox_props(mat):
    mat["sbxn"] = mat.get("sbxn", ["core", "jcesr", "vw", "shyamd", "kitchaev"])
    mat["sbxd"] = []

    for sbx in mat["sbxn"]:
        sbx_d = {k: get(mat, v) for k, v in SANDBOXED_PROPERTIES.items() if has(mat, k)}
        sbx_d["id"] = sbx
        mat["sbxd"].append(sbx_d)


def add_magnetism(mat, magnetism=None):

    # for historical consistency
    mag_types = {"NM": "Non-magnetic", "FiM": "Ferri", "AFM": "AFM", "FM": "FM"}

    struc = Structure.from_dict(mat["structure"])
    msa = CollinearMagneticStructureAnalyzer(struc)
    mat["magnetic_type"] = mag_types[msa.ordering.value]

    # this should never happen for future mats, and should have been fixed
    # for older mats, but just in case
    if 'magmom' not in struc.site_properties and mat['total_magnetization'] > 0.1:
        mat["magnetic_type"] = "Magnetic (unknown ordering)"

    # TODO: will deprecate the above from dedicated magnetism builder
    if magnetism:
        mat["magnetism"] = magnetism["magnetism"]


def add_bond_valence(mat, bond_valence):
    exclude_list = ['task_id', 'pymatgen_version', 'successful']
    if bond_valence.get('successful', False):
        for e in exclude_list:
            if e in bond_valence:
                del bond_valence[e]
        mat["bond_valence"] = bond_valence


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
    exclude_list = ['compliance_tensor_voigt', 'task_id', '_id',
                    'pretty_formula', 'inputs', 'last_updated']
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


def add_dielectric(mat, dielectric):

    if "dielectric" in dielectric:
        d = dielectric["dielectric"]

        mat["diel"] = {
            "e_electronic": d["static"],
            "e_total": d["total"],
            "n": np.sqrt(d["e_static"]),
            "poly_electronic": d["e_static"],
            "poly_total": d["e_static"]
        }

    if "piezo" in dielectric:
        d = dielectric["piezo"]

        mat["piezo"] = {"eij_max": d["e_ij_max"], "piezoelectric_tensor": d["total"], "v_max": d["max_direction"]}


def add_viewer_json(mat):
    """
    Generate JSON for structure viewer.
    """

    from mp_dash_components.converters.structure import StructureIntermediateFormat
    from mp_dash_components import __version__ as mp_dash_components_version
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


def add_dois(mat, doi):
    if "doi" in doi:
        mat["doi"] = doi["doi"]
    if "bibtex" in doi:
        mat["doi_bibtex"] = doi["bibtex"]

def add_meta(mat):

    meta = {
        'emmet_version': emmet_version,
        'pymatgen_version': pymatgen_version
    }
    mat['_meta'] = meta
