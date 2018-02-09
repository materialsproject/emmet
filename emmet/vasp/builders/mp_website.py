from datetime import datetime
import os
import string
import traceback
from pymongo import ASCENDING, DESCENDING

from monty.serialization import loadfn

from maggma.builder import Builder
from pydash.objects import get, set_, has


# Import for crazy things this builder needs
from pymatgen.io.cif import CifWriter
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.core.composition import Composition
from pymatgen import Structure
from pymatgen.matproj.snl import StructureNL
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.analysis.structure_analyzer import RelaxationAnalyzer
from pymatgen.analysis.diffraction.xrd import XRDPattern
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
mp_conversion_dict = loadfn(os.path.join(
    module_dir, "settings", "mp_conversion.json"))


SANDBOXED_PROPERTIES = {"e_above_hull": "e_above_hull",
                        "decomposes_to": "decomposes_to"}

latt_para_interval = [1.50 - 1.96 * 3.14, 1.50 + 1.96 * 3.14]
vol_interval = [4.56 - 1.96 * 7.82, 4.56 + 1.96 * 7.82]


class MPBuilder(Builder):

    def __init__(self, materials,  mp_materials, thermo=None, snls=None, xrd=None,
                 elasticity=None, piezo=None, icsd=None, bandstructure_fs="bandstructure_fs",
                 dos_fs="dos_fs", query=None,  **kwargs):
        """
        Creates a MP Website style materials doc.
        This builder is a bit unweildy as MP will eventually move to a new format
        Written for backwards compatability with previous infrastructure

        Args:
            tasks (Store): Store of task documents
            materials (Store): Store of materials documents
            mp_web (Store): Store of the mp style website docs
        """
        self.materials = materials
        self.mp_materials = mp_materials
        self.snls = snls
        self.thermo = thermo
        self.query = query if query else {}
        self.icsd = icsd
        self.xrd = xrd
        self.bandstructure_fs = bandstructure_fs
        self.dos_fs = dos_fs

        super().__init__(sources=list(filter(None, [materials, thermo, snls, elasticity, piezo, icsd, xrd])),
                         targets=[mp_materials],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need a new MP Style materials document

        Returns:
            generator of materials to calculate xrd
        """

        self.logger.info("MP Website Builder Started")

        # initialize the gridfs
        bfs = gridfs.GridFS(
            self.materials.collection.database, self.bandstructure_fs)
        dfs = gridfs.GridFS(self.materials.collection.database, self.dos_fs)

        # All relevant materials that have been updated since MP Website Materials
        # were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.mp_materials))
        mats = list(self.materials.distinct(self.materials.key, q))
        self.logger.info(
            "Found {} new materials for the website".format(len(mats)))

        for m in mats:
            doc = {"material": self.materials.query(
                criteria={self.materials.key: m}).limit(1)[0]}

            if self.thermo:
                doc["thermo"] = self.thermo.query(
                    criteria={self.thermo.key: m}).limit(1)[0]

            if self.snls:
                doc["snl"] = self.snls.query(
                    criteria={self.snls.key: m}).limit(1)[0]

            if self.icsd:
                doc["icsds"] = list(self.icsd.query(
                    criteria={"chemsys": doc["material"]["chemsys"]}))

            if self.magnetism:
                doc["magnetism"] = self.magnetism.query(
                    criteria={self.magnetism.key: m}).limit(1)[0]

            if self.xrd:
                doc["xrd"] = self.xrd.query(
                    criteria={self.xrd.key: m}).limit(1)[0]

            yield doc

    def process_item(self, item):

        new_mat = item["material"]

        mat = old_style_mat(new_mat)
        add_bv_structure(mat)
        add_cifs(mat)
        sandbox_props(mat)
        add_blessed_tasks(mat,new_mat)
        
        if "xrd" in item:
            xrd = item["xrd"]
            add_xrd(mat, xrd)

        if "thermo" in item:
            thermo = item["thermo"]
            add_thermo(mat, thermo)

        if "snl" in item:
            snl = item["snl"]
            add_snl(mat, snl)

            if "icsds" in item:
                icsds = item["icsds"]
                if icsds:
                    add_icsd(mat, icsds)

        return jsanitize(mat)

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([[dict]]): a list of list of thermo dictionaries to update
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info(
                "Updating {} mp materials docs".format(len(items)))
            self.mp_materials.update(docs=items)
        else:
            self.logger.info("No items to update")

#
#
#
#
# THIS SECTION DEFINES EXTRA FUNCTIONS THAT MODIFY THE DOC PER MP CRAZY SETTINGS
#
#

def old_style_mat(new_mat):

    mat = {}
    for mp,new_key in mp_conversion_dict.items():
        if has(new_mat,new_key):
            set_(mat,mp,get(new_mat,new_key))


    mat["is_orderd"] = True
    mat["is_compatible"] = True

    struc = Structure.from_dict(mat["structure"])
    mat["oxide_type"] = oxide_type(struc)
    mat["reduced_cell_formula"] = struc.composition.as_dict()
    mat["full_formula"] = "".join(struc.formula.split())
    vals = sorted(mat["reduced_cell_formula"].values())
    mat["anonymous_formula"] = {string.ascii_uppercase[i]: float(vals[i])
                                for i in range(len(vals))}

    set_(mat,"original_task_id",get(new_mat,"material_id"))
    set_(mat,"ntask_ids",len(get(new_mat,"task_ids")))

    set_(mat,"input.incar",get(new_mat,"inputs.structure_optimization.incar"))
    set_(mat,"input.kpoints",get(new_mat,"inputs.structure_optimization.kpoints"))
    set_(mat,"encut",get(new_mat,"inputs.structure_optimization.incar.ENCUT"))
    mat["pseudo_potential"] = {
        "pot_type": "paw",
        "labels" : get(new_mat, "input.structure_optimization.potcar.symbols"),
        "functional": get(new_mat, "input.structure_optimization.potcar.functional")
    }

    return mat

def add_blessed_tasks(mat,new_mat):
    blessed_tasks = {}
    for doc in new_mat["origins"]:
        blessed_tasks[doc["task_type"]] = doc["task_id"]

    mat["blessed_tasks"] = blessed_tasks

def add_bv_structure(doc):
    struc = Structure.from_dict(doc["structure"])
    try:
        bva = BVAnalyzer()
        bv_struct = bva.get_oxi_state_decorated_structure(struc)
        doc["bv_structure"] = bv_struct.as_dict()
    except Exception as e:
        print("BVAnalyzer error: {}".format(e))

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
        _log.error("Can't get alternative cells for task_id {i}".format(
            i=doc["task_id"]))


def add_xrd(mat, xrd):
    mat["xrd"] = {}
    for el, doc in xrd["xrd"].items():
        el_doc = {}
        el_doc["meta"] = ["amplitude", "hkl", "two_theta", "d_spacing"]
        el_doc["created_at"] = datetime.now().isoformat()
        el_doc["wavelength"] = doc["wavelength"]

        xrd_pattern = XRDPattern.from_dict(doc["pattern"])
        el_doc["pattern"] = [[float(intensity),
                              [int(x) for x in eval(list(hkls.keys())[0])],
                              two_theta,
                              float(d_hkl)] for two_theta, intensity, hkls, d_hkl in zip(xrd_pattern.x,
                                                                                         xrd_pattern.y,
                                                                                         xrd_pattern.hkls,
                                                                                         xrd_pattern.d_hkls)]

        mat["xrd"][el] = el_doc

def add_thermo(mat, thermo):
    if has(thermo,"thermo.e_above_hull"):
        set_(mat,"e_above_hull",get(thermo,"thermo.e_above_hull"))

    if has(thermo,"thermo.formation_energy_per_atom"):
        set_(mat,"formation_energy_per_atom",get(thermo,"thermo.formation_energy_per_atom"))

    if has(thermo,"thermo.decmposes_to"):
        set_(mat,"decmposes_to",get(thermo,"thermo.decmposes_to"))

def sandbox_props(mat):
    mat["sbxn"] = mat["sbxn"] if mat["sbxn"] else ["core"]
    mat["sbxd"] = []

    for sbx in mat["sbxn"]:
        sbx_d = {k: get(mat, v)
                 for k, v in SANDBOXED_PROPERTIES.items() if has(mat, k)}
        sbx_d["id"] = sbx
        mat["sbxd"].append(sbx_d)

def add_icsd(mat, icsds):

    relevant_icsd = [icsd for icsd in icsds if icsd[
        "icsd_id"] in mat.get("icsd_ids", [])]
    results = []
    for icsd in relevant_icsd:
        result = {"warnings": []}
        tags = [icsd[t]
                for t in ["chem_name", "min_name"] if t in icsd and icsd[t]]
        result["exp"] = {'pressure': icsd["pressure"], 'tags': tags}
        if icsd.get('pressure', 0) > 1:
            result["warnings"].append("High pressure experimental phase.")
        results.append(result)

    if len(results) == 0:
        results.append({"warnings": ["Structure has been removed in the 2012 version of ICSD."],
                        "exp": {}})

    if mat["icsd_ids"]:
        results[0]["exp_lattice"] = mat["snl"]["lattice"]

    # Check relaxation
    orig_crystal = Structure.from_dict(mat["snl"])
    final_structure = Structure.from_dict(mat["structure"])

    try:
        analyzer = RelaxationAnalyzer(orig_crystal, final_structure)
        latt_para_percentage_changes = analyzer.get_percentage_lattice_parameter_changes()
        for l in ["a", "b", "c"]:
            change = latt_para_percentage_changes[l] * 100
            if change < latt_para_interval[0] or change > latt_para_interval[1]:
                results[0]["warnings"].append(
                    "Large change in {} lattice parameter during relaxation.".format(l))
        change = analyzer.get_percentage_volume_change() * 100
        if change < vol_interval[0] or change > vol_interval[1]:
            results[0]["warnings"].append(
                "Large change in volume during relaxation.")
    except Exception as ex:
        # print icsd_crystal.formula
        # print final_structure.formula
        print("Relaxation analyzer failed for Material:{} due to {}".format(
            mat["task_id"], traceback.print_exc()))

    # Merge all the results

    if len(results) > 1:

        results_union = {"exp": {"tags": []}, "warnings": []}
        tags = []
        warnings = []
        for i in results:
            if i.get("exp_lattice"):
                results_union["exp_lattice"] = i["exp_lattice"]
            if i.get("exp"):
                if i["exp"].get("tags"):
                    tags.extend(i["exp"]["tags"])
            if i.get("warnings"):
                warnings.extend(i["warnings"])
        if tags:
            results_union["exp"]["tags"] = [i for i in set(tags)]
        if warnings:
            high_pressure_count = 0
            for w in warnings:
                if w == "High pressure experimental phase.":
                    high_pressure_count += 1
            results_union["warnings"] = [i for i in set(warnings)]
            if high_pressure_count != 0 and high_pressure_count != len(mat.get("icsd_ids", [])):
                results_union["warnings"].remove(
                    "High pressure experimental phase.")
        results = results_union
    else:
        results = results[0]

    if results.get("exp_lattice"):
        mat["exp_lattice"] = results["exp_lattice"]
    mat["exp"] = results["exp"]
    mat["warnings"] = results["warnings"]


def add_magnetism(mat, mag=None):

    mag_types = {"NM": "Non-magnetic",
                 "FiM": "Ferri",
                 "AFM": "AFM",
                 "FM": "FM"}

    struc = Structure.from_dict(mat["structure"])
    msa = CollinearMagneticStructureAnalyzer(struc)
    mat["magnetic_type"] = mag_types[msa.ordering.value]


def add_elasticity(mat, elasticity):
    mat["elasticity"] = elasticity["elasticity"]


def add_piezo(mat, piezo):
    mat["piezo"] = piezo["piezo"]

def add_diel(mat,diel):
    mat["diel"] = diel["diel"]

def add_snl(mat, snl=None):
    mat["snl"] = snl.get("snl", None)
    mat["snl_final"] = snl.get("snl", None)
    mat["created_at"] = get(snl,"snl.about.created_at") if has(snl,"snl.about.created_at") else None
    mat["icsd_ids"] = snl.get("icsd_ids", [])
    