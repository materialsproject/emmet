from datetime import datetime
import os
import string
import traceback
from ast import literal_eval
from pymongo import ASCENDING, DESCENDING

from monty.serialization import loadfn
from monty.json import jsanitize

from maggma.builder import Builder
from pydash.objects import get, set_, has

# Import for crazy things this builder needs
from pymatgen.io.cif import CifWriter
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.core.composition import Composition
from pymatgen import Structure
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.analysis.structure_analyzer import RelaxationAnalyzer
from pymatgen.analysis.diffraction.xrd import XRDPattern
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer

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
    "total_magnetization": "magnestism.total_magnetization",
    "unit_cell_formula": "composition",
    "volume": "volume",
    "warnings": "analysis.warnings",
    "task_ids": "task_ids",
    "task_id": "task_id",
    "original_task_id": "task_id",
    "input.incar": "inputs.structure_optimization.incar",
    "input.kpoints": "inputs.structure_optimization.kpoints",
    "encut": "inputs.structure_optimization.incar.ENCUT"
}

SANDBOXED_PROPERTIES = {"e_above_hull": "e_above_hull", "decomposes_to": "decomposes_to"}

latt_para_interval = [1.50 - 1.96 * 3.14, 1.50 + 1.96 * 3.14]
vol_interval = [4.56 - 1.96 * 7.82, 4.56 + 1.96 * 7.82]


class MPBuilder(Builder):
    def __init__(self,
                 materials,
                 mp_materials,
                 thermo=None,
                 electronic_structure=None,
                 magnetism=None,
                 snls=None,
                 xrd=None,
                 elasticity=None,
                 piezo=None,
                 icsd=None,
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
        self.snls = snls
        self.thermo = thermo
        self.query = query if query else None
        self.icsd = icsd
        self.xrd = xrd
        self.elasticity = elasticity
        self.piezo = piezo
        self.magnetism = magnetism

        sources = list(
            filter(None, [materials, thermo, electronic_structure, magnetism, snls, elasticity, piezo, icsd, xrd]))

        super().__init__(sources=sources, targets=[mp_materials], **kwargs)

    def get_items(self):
        """
        Gets all materials that need a new MP Style materials document

        Returns:
            generator of materials to calculate xrd
        """

        self.logger.info("MP Website Builder Started")

        # All relevant materials that have been updated since MP Website Materials
        # were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.mp_materials))
        mats = list(self.materials.distinct(self.materials.key, q))
        self.logger.info("Found {} new materials for the website".format(len(mats)))

        for m in mats:

            doc = {"material": self.materials.query_one(criteria={self.materials.key: m})}

            if self.electronic_structure:
                doc["electronic_structure"] = self.electronic_structure.query_one(criteria={
                    self.electronic_structure.key: m,
                    "band_gap": {
                        "$exists": 1
                    }
                })

            if self.elasticity:
                doc["elasticity"] = self.elasticity.query_one(criteria={self.elasticity.key: m})

            if self.piezo:
                doc["piezo"] = self.piezo.query_one(criteria={self.piezo.key: m})

            if self.thermo:
                doc["thermo"] = self.thermo.query_one(criteria={self.thermo.key: m})

            if self.snls:
                doc["snl"] = self.snls.query_one(criteria={self.snls.key: m})

            if self.icsd:
                doc["icsds"] = list(self.icsd.query(criteria={"chemsys": doc["material"]["chemsys"]}))

            if self.magnetism:
                doc["magnetism"] = self.magnetism.query_one(criteria={self.magnetism.key: m})

            if self.xrd:
                doc["xrd"] = self.xrd.query_one(criteria={self.xrd.key: m})

            self.logger.debug("Working on {}".format(m))
            yield doc

    def process_item(self, item):

        new_style_mat = item["material"]

        mat = old_style_mat(new_style_mat)
        add_es(mat, new_style_mat)

        if item.get("xrd", None):
            xrd = item["xrd"]
            add_xrd(mat, xrd)

        if item.get("piezo", None):
            pass

        if item.get("elasticity", None):
            pass

        if item.get("thermo", None):
            thermo = item["thermo"]
            add_thermo(mat, thermo)

        if item.get("snl", None):
            snl = item["snl"]
            add_snl(mat, snl)

        sandbox_props(mat)
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
            self.mp_materials.update(docs=items)
        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections
        :return:
        """

        # Basic search index for tasks
        self.tasks.ensure_index("task_id", unique=True)
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")
        self.tasks.ensure_index(self.tasks.lu_field)

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

    mat["is_orderd"] = True
    mat["is_compatible"] = True

    struc = Structure.from_dict(mat["structure"])
    mat["oxide_type"] = oxide_type(struc)
    mat["reduced_cell_formula"] = struc.composition.as_dict()
    mat["full_formula"] = "".join(struc.formula.split())
    vals = sorted(mat["reduced_cell_formula"].values())
    mat["anonymous_formula"] = {string.ascii_uppercase[i]: float(vals[i]) for i in range(len(vals))}

    set_(mat, "pseudo_potential.functional", "PBE")

    set_(mat, "pseudo_potential.labels", [p["titel"].split()[1] for p in get(new_style_mat, "calc_settings.potcar_spec")])
    mat["ntask_ids"] = len(get(new_style_mat, "task_ids"))
    set_(mat, "pseudo_potential.pot_type", "paw")
    add_blessed_tasks(mat, new_style_mat)
    add_cifs(mat)
    check_relaxation(mat,new_style_mat)

    return mat


def add_es(mat, new_style_mat):

    bs_origin = None
    dos_origin = None
    try:
        bs_origin = next((origin for origin in new_style_mat.get("origins", []) if "Line" in origin["task_type"]), None)
        dos_origin = next((origin for origin in new_style_mat.get("origins", []) if "Uniform" in origin["task_type"]), None)

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


def add_cifs(doc):
    struc = Structure.from_dict(doc["structure"])
    sym_finder = SpacegroupAnalyzer(struc, symprec=0.1)
    doc["cif"] = str(CifWriter(struc))
    doc["cifs"] = {}
    if sym_finder.get_hall():
        primitive = sym_finder.get_primitive_standard_structure()
        conventional = sym_finder.get_conventional_standard_structure()
        refined = sym_finder.get_refined_structure()
        doc["cifs"]["primitive"] = str(CifWriter(primitive))
        doc["cifs"]["refined"] = str(CifWriter(refined))
        doc["cifs"]["conventional_standard"] = str(CifWriter(conventional))
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

        xrd_pattern = XRDPattern.from_dict(doc["pattern"])
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

    if has(thermo, "thermo.decmposes_to"):
        set_(mat, "decmposes_to", get(thermo, "thermo.decmposes_to"))


def sandbox_props(mat):
    mat["sbxn"] = mat.get("sbxn", ["core","jcesr","vw","shyamd","kitchaev"])
    mat["sbxd"] = []

    for sbx in mat["sbxn"]:
        sbx_d = {k: get(mat, v) for k, v in SANDBOXED_PROPERTIES.items() if has(mat, k)}
        sbx_d["id"] = sbx
        mat["sbxd"].append(sbx_d)


def add_magnetism(mat):
    mag_types = {"NM": "Non-magnetic", "FiM": "Ferri", "AFM": "AFM", "FM": "FM"}

    struc = Structure.from_dict(mat["structure"])
    msa = CollinearMagneticStructureAnalyzer(struc)
    mat["magnetic_type"] = mag_types[msa.ordering.value]

def add_snl(mat, snl=None):    
    mat["snl"] = copy.deepcopy(mat["structre"])
    if snl:
        mat["snl"].update(snl)

    mat["snl_final"] = mat["snl"]
    mat["icsd_ids"] = get(snl,"data._db_ids.icsd_ids",[])
    mat["tags"] = snl["remarks"]

def check_relaxation(mat,new_style_mat):
    final_structure = Structure.from_dict(mat["structure"])

    warnings = []
    for init_struc in new_style_mat["initial_structures"]:
        # Check relaxation
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

    mat["warnings"] = warnings
