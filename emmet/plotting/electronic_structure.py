import io
import traceback
from maggma.builders import Builder
from pydash.objects import get
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine, BandStructure
from pymatgen.symmetry.bandstructure import HighSymmKpath
from pymatgen.electronic_structure.dos import CompleteDos
from sumo.plotting.dos_plotter import SDOSPlotter
from sumo.plotting.bs_plotter import SBSPlotter
from sumo.electronic_structure.dos import get_pdos

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class ElectronicStructureImageBuilder(Builder):
    def __init__(self, materials, electronic_structure, bandstructures, dos, query=None, plot_options=None, **kwargs):
        """
        Creates an electronic structure from a tasks collection, the associated band structures and density of states, and the materials structure

        Really only usefull for MP Website infrastructure right now.

        materials (Store) : Store of materials documents
        electronic_structure  (Store) : Store of electronic structure documents
        bandstructures (Store) : store of bandstructures
        dos (Store) : store of DOS
        plot_options (dict): options to pass to the sumo SBSPlotter
        query (dict): dictionary to limit tasks to be analyzed
        """

        self.materials = materials
        self.electronic_structure = electronic_structure
        self.bandstructures = bandstructures
        self.dos = dos
        self.query = query if query else {}
        self.plot_options = plot_options if plot_options else {}

        super().__init__(sources=[materials, bandstructures, dos], targets=[electronic_structure], **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Electronic Structure Builder Started")

        # get all materials without an electronic_structure document but bandstructure and dos fields
        # and there is either a dos or bandstructure
        q = dict(self.query)
        q["$and"] = [{"bandstructure.bs_task": {"$exists": 1}}, {"bandstructure.dos_task": {"$exists": 1}}]
        mat_ids = list(self.materials.distinct(self.materials.key, criteria=q))
        es_ids = self.electronic_structure.distinct("task_id")

        # get all materials that were updated since the electronic structure was last updated
        # and there is either a dos or bandstructure
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.electronic_structure))
        q["$and"] = [{"bandstructure.bs_task": {"$exists": 1}}, {"bandstructure.dos_task": {"$exists": 1}}]
        mats = set(self.materials.distinct(self.materials.key, criteria=q)) | (set(mat_ids) - set(es_ids))

        self.logger.debug("Processing {} materials for electronic structure".format(len(mats)))

        self.total = len(mats)

        for m in mats:
            mat = self.materials.query_one([self.materials.key, "structure", "bandstructure", "inputs"],
                                           {self.materials.key: m})
            mat["bandstructure"]["bs"] = self.bandstructures.query_one(
                criteria={"task_id": get(mat, "bandstructure.bs_task")})

            mat["bandstructure"]["dos"] = self.dos.query_one(criteria={"task_id": get(mat, "bandstructure.dos_task")})
            yield mat

    def process_item(self, mat):
        """
        Process the tasks and materials into just a list of materials

        Args:
            mat (dict): material document

        Returns:
            (dict): electronic_structure document
        """
        d = {self.electronic_structure.key: mat[self.materials.key]}
        self.logger.info("Processing: {}".format(mat[self.materials.key]))

        bs = build_bs(mat["bandstructure"]["bs"], mat)
        dos = CompleteDos.from_dict(mat["bandstructure"]["dos"])

        if bs and dos:
            try:
                pdos = get_pdos(dos)
                dos_plotter = SDOSPlotter(dos, pdos)
                bs_plotter = SBSPlotter(bs)
                plt = bs_plotter.get_plot(dos_plotter=dos_plotter, **self.plot_options)
                d["plot"] = image_from_plot(plt)
                plt.close()
            except Exception:
                traceback.print_exc()
                self.logger.warning("Caught error in bandstructure plotting for {}: {}".format(
                    mat[self.materials.key], traceback.format_exc()))

        # Reduced Band structure plot
        try:
            gap = bs.get_band_gap()["energy"]
            plot_data = bs_plotter.bs_plot_data()
            d["bs_plot_small"] = get_small_plot(plot_data, gap)
        except Exception:
            self.logger.warning("Caught error in generating reduced bandstructure plot for {}: {}".format(
                mat[self.materials.key], traceback.format_exc()))

        # Store task_ids
        for k in ["bs_task", "dos_task", "uniform_task"]:
            if k in mat["bandstructure"]:
                d[k] = mat["bandstructure"][k]

        return d

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} electronic structure docs".format(len(items)))
            self.electronic_structure.update(items)
        else:
            self.logger.info("No electronic structure docs to update")


def get_small_plot(plot_data, gap):
    for branch in plot_data['energy']:
        for spin, v in branch.items():
            new_bands = []
            for band in v:
                if min(band) < gap + 3 and max(band) > -3:
                    new_bands.append(band)
                else:
                    new_bands.append([])
            branch[spin] = new_bands
    return plot_data


def image_from_plot(plot):
    imgdata = io.BytesIO()
    plot.tight_layout()
    plot.savefig(imgdata, format="png", dpi=100)
    plot_img = imgdata.getvalue()
    return plot_img


def build_bs(bs_dict, mat):

    bs_dict["structure"] = mat["structure"]

    # Add in High Symm K Path if not already there
    if len(bs_dict.get("labels_dict", {})) == 0:
        labels = get(mat, "inputs.nscf_line.kpoints.labels", None)
        kpts = get(mat, "inputs.nscf_line.kpoints.kpoints", None)
        if labels and kpts:
            labels_dict = dict(zip(labels, kpts))
            labels_dict.pop(None, None)
        else:
            struc = Structure.from_dict(bs_dict["structure"])
            labels_dict = HighSymmKpath(struc)._kpath["kpoints"]

        bs_dict["labels_dict"] = labels_dict

    # This is somethign to do with BandStructureSymmLine's from dict being problematic
    bs = BandStructureSymmLine.from_dict(bs_dict)

    return bs
