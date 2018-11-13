import logging
import tempfile
import gridfs
import os

from abipy.dfpt.phonons import get_dyn_mat_eigenvec, match_eigenvectors
from abipy.dfpt.anaddbnc import AnaddbNcFile
from monty.json import jsanitize
from pymatgen.phonon.bandstructure import PhononBandStructureSymmLine
from pymatgen.core.structure import Structure
from pymatgen.io.abinit.abiobjects import KSampling
from pymatgen.symmetry.bandstructure import HighSymmKpath
import numpy as np
from abipy.abio.inputs import AnaddbInput
from abipy.core.abinit_units import Ha_cmm1
from abipy.flowtk.tasks import AnaddbTask, TaskManager
from abipy.dfpt.ddb import AnaddbError
from abipy.core.abinit_units import eV_to_THz

from maggma.builders import Builder


#TODO - handle possible other sources for the anaddb netcdf files?
#     - add input more parameters to tune anaddb calculation?
#     - identify the warning for the materials? (e.g. large ASR and CNSR breaking)
#     - add a second collection with the phononwebsite format?
#     - store the anaddb netcdf output to speedup possible rerunning of the builder?
#     - store the PhononBandStructureSymmLine in gridfs

class PhononBuilder(Builder):
    def __init__(self, materials, phonon, query=None, **kwargs):
        """
        CCreates a phonon collection for materials

        Args:
            materials (Store): Store of materials documents
            phonon (Store): Store of diffraction data such as formation energy and decomposition pathway
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.phonon = phonon

        if query is None:
            query = {}
        self.query = query

        super().__init__(sources=[materials],
                         targets=[phonon],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need phonons

        Returns:
            generator of materials to calculate xrd
        """

        self.logger.info("Phonon Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # All relevant materials that have been updated since diffraction props were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.phonon))
        mats = list(self.materials.find(q, {"mp_id": 1}))
        self.logger.info("Found {} new materials for phonon data".format(len(mats)))

        # list of properties queried from the results DB
        # basic informations
        projection = {"mp_id": 1, "spacegroup.number":1}
        # input data
        projection.update({"abinit_input.structure": 1, "abinit_input.ngkpt": 1, "abinit_input.shiftk": 1,
                           "abinit_input.ecut": 1, "abinit_input.ngqpt": 1})
        # file ids to be fetched
        projection["abinit_output.ddb_id"] = 1

        # initialize the gridfs
        ddbfs = gridfs.GridFS(self.materials().database, "ddb_fs")

        for m in mats:
            item = self.materials().find_one(m, projection)

            # download the DDB file and add the path to the item
            with tempfile.NamedTemporaryFile() as f:
                f.write(ddbfs.get(m["abinit_output.ddb_id"]).read())
                item["ddb_path"] = f.name

            yield item

    def process_item(self, item):
        """
        Generates the full phonon document from an item

        Args:
            item (dict): a dict extracted from the phonon calculations results and the path of the
                downloaded DDB file.

        Returns:
            dict: a diffraction dict
        """
        self.logger.debug("Processing phonon item for {}".format(item['mp_id']))

        try:

            structure = Structure.from_dict(item["abinit_input.structure"])

            ph_doc = {"structure": structure.as_dict()}
            ph_doc["phonon"] = self.get_phonon_properties(item)
            ph_doc[self.phonon.key] = item[self.materials.key]

            return ph_doc
        except Exception as e:
            self.logger.warning(
                "Error generating the phonon properties for {}: {}".format(item["mp_id"], e))
            return None

    def get_phonon_properties(self, item):
        """
        Extracts the phonon properties from the item
        """

        # the temp dir should still exist when using the objects as some readings are done lazily
        with tempfile.TemporaryDirectory() as workdir:
            phbst_file, phdos_file, ananc_file, labels_list = self.run_anaddb(item, workdir=workdir)

            phbands = phbst_file.phbands
            phbands.read_non_anal_from_file(phbst_file.filepath)

            symm_line_bands = self.get_pmg_bs(phbands, labels_list)

            complete_dos = phdos_file.to_pymatgen()
            phdos = phdos_file.phdos

            tstart, tstop, nt = 5, 800, 160
            temp = np.linspace(tstart, tstop, nt)

            thermo = {"temperature": temp.tolist(),
                      "entropy": phdos.get_entropy(tstart, tstop, nt).values.tolist(),
                      "cv": phdos.get_cv(tstart, tstop, nt).values.tolist(),
                      "free_energy": phdos.get_free_energy(tstart, tstop, nt).values.tolist(),
                      }

            data = {"dos": complete_dos.as_dict(),
                    "bs": symm_line_bands.as_dict(),
                    "thermodynamic": thermo,
                    "becs": ananc_file.becs.values.tolist()}

            return jsanitize(data)

    def run_anaddb(self, item, workdir):
        """
        Runs anaddb an reads the outputs
        """

        anaddb_inp, labels_list = self.get_anaddb_input(item)

        #TODO should this be an input?
        tm = TaskManager.from_user_config()

        ddb_path = item["ddb_path"]

        task = AnaddbTask.temp_shell_task(anaddb_inp, ddb_node=ddb_path, workdir=workdir, manager=tm)

        # Run the task here.
        task.start_and_wait(autoparal=False)

        report = task.get_event_report()
        if not report.run_completed:
            raise AnaddbError(task=task, report=report)

        phbst_file = task.open_phbst()
        phdos_file = task.open_phdos()
        ananc_file = AnaddbNcFile.from_file(os.path.join(workdir, "anaddb.nc"))

        return phbst_file, phdos_file, ananc_file, labels_list



    def get_anaddb_input(self, item):
        """
        creates the AnaddbInput object. It also returns the list of qpoints labels for generating the
        PhononBandStructureSymmLine.
        """

        ngqpt = item["abinit_input.ngqpt"]
        q1shft = [(0, 0, 0)]

        structure = Structure.from_dict(item["abinit_input.structure"])

        hs = HighSymmKpath(structure, symprec=1e-2)

        spgn = hs._sym.get_space_group_number()
        if spgn != item["spacegroup.number"]:
            raise RuntimeError("Parsed specegroup number {} does not match "
                               "calculation spacegroup {}".format(spgn, item["spacegroup.number"]))

        # for the moment use gaussian smearing
        prtdos = 1
        dossmear = 3 / Ha_cmm1
        lo_to_splitting = True
        dipdip = 1
        asr = 2
        chneut = 1
        ng2qppa = 50000

        inp = AnaddbInput(structure, comment="ANADB input for phonon bands and DOS")

        inp.set_vars(
            ifcflag=1,
            ngqpt=np.array(ngqpt),
            q1shft=q1shft,
            nqshft=len(q1shft),
            asr=asr,
            chneut=chneut,
            dipdip=dipdip,
        )

        # Parameters for the dos.
        ng2qpt = KSampling.automatic_density(structure, kppa=ng2qppa).kpts[0]
        inp.set_vars(prtdos=prtdos, dosdeltae=None, dossmear=dossmear, ng2qpt=ng2qpt)

        # Parameters for the BS
        qpts, labels_list = hs.get_kpoints(line_density=18, coords_are_cartesian=False)

        n_qpoints = len(qpts)
        qph1l = np.zeros((n_qpoints, 4))

        qph1l[:, :-1] = qpts
        qph1l[:, -1] = 1

        inp['qph1l'] = qph1l.tolist()
        inp['nph1l'] = n_qpoints


        if lo_to_splitting:
            kpath = hs.kpath
            directions = []
            for qptbounds in kpath['path']:
                for i, qpt in enumerate(qptbounds):
                    if np.array_equal(kpath['kpoints'][qpt], (0, 0, 0)):
                        # anaddb expects cartesian coordinates for the qph2l list
                        if i > 0:
                            directions.extend(structure.lattice.reciprocal_lattice_crystallographic.get_cartesian_coords(
                                kpath['kpoints'][qptbounds[i - 1]]))
                            directions.append(0)

                        if i < len(qptbounds) - 1:
                            directions.extend(structure.lattice.reciprocal_lattice_crystallographic.get_cartesian_coords(
                                kpath['kpoints'][qptbounds[i + 1]]))
                            directions.append(0)

            if directions:
                directions = np.reshape(directions, (-1, 4))
                inp.set_vars(
                    nph2l=len(directions),
                    qph2l=directions
                )

        return inp, labels_list

    def get_pmg_bs(self, phbands, labels_list):
        """
        Generates a PhononBandStructureSymmLine starting from a abipy PhononBands object

        Args:
            phbands: abipy PhononBands
            labels_list: list of labels used to generate the path
        Returns:
            An instance of PhononBandStructureSymmLine
        """

        structure = phbands.structure

        n_at = len(structure)

        qpts = np.array(phbands.qpoints.frac_coords)
        ph_freqs = np.array(phbands.phfreqs)
        displ = np.array(phbands.phdispl_cart)

        labels_dict = {}

        for i, (q, l) in enumerate(zip(qpts, labels_list)):
            if l:
                labels_dict[l] = q
                # set LO-TO at gamma
                if "Gamma" in l:
                    if i > 0 and not labels_list[i-1]:
                        ph_freqs[i] = phbands._get_non_anal_freqs(qpts[i-1])
                        displ[i] = phbands._get_non_anal_phdispl(qpts[i-1])
                    if i < len(qpts)-1 and not labels_list[i+1]:
                        ph_freqs[i] = phbands._get_non_anal_freqs(qpts[i+1])
                        displ[i] = phbands._get_non_anal_phdispl(qpts[i+1])

        ind = self.match_bands(displ, phbands.structure, phbands.amu)

        ph_freqs = ph_freqs[np.arange(len(ph_freqs))[:, None], ind]
        displ = displ[np.arange(displ.shape[0])[:, None, None],
                      ind[..., None],
                      np.arange(displ.shape[2])[None, None, :]]

        ph_freqs = np.transpose(ph_freqs) * eV_to_THz
        displ = np.transpose(np.reshape(displ, (len(qpts), 3*n_at, n_at, 3)), (1, 0, 2, 3))

        return PhononBandStructureSymmLine(qpoints=qpts, frequencies=ph_freqs,
                                           lattice=structure.reciprocal_lattice,
                                           has_nac=phbands.non_anal_ph is not None, eigendisplacements=displ,
                                           labels_dict=labels_dict, structure=structure)

    def match_bands(self, displ, structure, amu):
        """
        Match the phonon bands of neighboring q-points based on the scalar product of the eigenvectors
        """
        eigenvectors = get_dyn_mat_eigenvec(displ, structure, amu)
        ind = np.zeros(displ.shape[0:2], dtype=np.int)

        ind[0] = range(displ.shape[1])

        for i in range(1, len(eigenvectors)):
            match = match_eigenvectors(eigenvectors[i - 1], eigenvectors[i])
            ind[i] = [match[m] for m in ind[i - 1]]

        return ind

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([[dict]]): a list of list of phonon dictionaries to update
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} phonon docs".format(len(items)))
            self.phonon.update(docs=items)
        else:
            self.logger.info("No items to update")


    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections
        :return:
        """
        # Search index for materials
        self.materials.ensure_index(self.materials.key, unique=True)

        # Search index for materials
        self.phonon.ensure_index(self.diffraction.key, unique=True)
