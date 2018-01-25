import logging
import tempfile
import gridfs
import os

from abipy.dfpt.phonons import get_dyn_mat_eigenvec, match_eigenvectors, PhbstFile, PhdosFile
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

from maggma.builder import Builder


#TODO - handle possible other sources for the anaddb netcdf files?
#     - add input more parameters to tune anaddb calculation?
#     - store the anaddb netcdf output to speedup possible rerunning of the builder?


class PhononBuilder(Builder):
    def __init__(self, materials, phonon, phonon_bs, ddb_files, query=None,
                 manager=None, **kwargs):
        """
        Creates a phonon collection for materials.

        Args:
            materials (Store): source Store of materials documents
            phonon (Store): target Store of the phonon properties
            phonon_bs (Store): target Store for the phonon band structure. The document may
                exceed the 16MB limit of the mongodb collections.
            ddb_files (Store): target Store of the DDB files. The document may
                exceed the 16MB limit of the mongodb collections.
            query (dict): dictionary to limit materials to be analyzed
            manager (TaskManager): an instance of the abipy TaskManager. If None it will be
                generated from user configuration.
        """

        self.materials = materials
        self.phonon = phonon
        self.phonon_bs = phonon_bs
        self.ddb_files = ddb_files

        if query is None:
            query = {}
        self.query = query

        if manager is None:
            self.manager = TaskManager.from_user_config()
        else:
            manager = manager

        super().__init__(sources=[materials],
                         targets=[phonon, phonon_bs, ddb_files],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need phonons

        Returns:
            generator of materials to extract phonon properties
        """

        self.logger.info("Phonon Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # All relevant materials that have been updated since phonon props were last calculated
        q = dict(self.query)
        # GridFSStore currently does not handle this operation. Only check on self.phonon Store.
        q.update(self.materials.lu_filter(self.phonon))
        self.logger.debug("Filtering materials by {}".format(q))
        mats = list(self.materials.query(criteria=q, properties={"mp_id": 1}))
        self.logger.info("Found {} new materials for phonon data".format(len(mats)))

        # list of properties queried from the results DB
        # basic informations
        projection = {"mp_id": 1, "spacegroup.number":1}
        # input data
        input_attr_list = ["structure", "ngkpt", "shiftk", "ecut", "ngqpt", "occopt", "tsmear"]
        projection.update({"abinit_input.{}".format(i): 1 for i in input_attr_list})
        # file ids to be fetched
        projection["abinit_output.ddb_id"] = 1

        # initialize the gridfs
        ddbfs = gridfs.GridFS(self.materials.collection.database, "ddb_fs")

        for m in mats:
            item = self.materials.query_one(properties=projection, criteria={self.materials.key: m[self.materials.key]})

            # download the DDB file and add the path to the item
            with tempfile.NamedTemporaryFile(suffix="_DDB", delete=False) as f:
                f.write(ddbfs.get(item["abinit_output"]["ddb_id"]).read())
                item["ddb_path"] = f.name

            yield item

    def process_item(self, item):
        """
        Generates the full phonon document from an item

        Args:
            item (dict): a dict extracted from the phonon calculations results and the path of the
                downloaded DDB file.

        Returns:
            dict: a dict with phonon data
        """
        self.logger.debug("Processing phonon item for {}".format(item['mp_id']))

        try:

            structure = Structure.from_dict(item["abinit_input"]["structure"])

            ph_data = {"structure": structure.as_dict()}
            ph_data["abinit_input_vars"] = self.abinit_input_vars(item)
            ph_data["phonon"] = self.get_phonon_properties(item)
            sr_break = self.get_sum_rule_breakings(item)
            ph_data["sum_rules_breaking"] = sr_break
            ph_data["warnings"] = self.get_warnings(sr_break["asr"], sr_break["cnsr"], ph_data["phonon"]["ph_bs"])
            ph_data[self.phonon.key] = item["mp_id"]

            # extract the DDB as a string
            with open(item['ddb_path'], 'rt') as f:
                ph_data['ddb_str'] = f.read()

            return jsanitize(ph_data)
        except Exception as e:
            self.logger.warning(
                "Error generating the phonon properties for {}: {}".format(item["mp_id"], e))
            raise
            return None

    def get_phonon_properties(self, item):
        """
        Extracts the phonon properties from the item
        """

        # the temp dir should still exist when using the objects as some readings are done lazily
        with tempfile.TemporaryDirectory() as workdir:
            anaddb_input, labels_list = self.get_properties_anaddb_input(item)
            task = self.run_anaddb(ddb_path=item["ddb_path"], anaddb_input=anaddb_input, workdir=workdir)

            with task.open_phbst() as phbst_file:
                phbands = phbst_file.phbands
                phbands.read_non_anal_from_file(phbst_file.filepath)
                symm_line_bands = self.get_pmg_bs(phbands, labels_list)

            with task.open_phdos() as phdos_file:
                complete_dos = phdos_file.to_pymatgen()

            with AnaddbNcFile(os.path.join(workdir, "anaddb.nc")) as ananc_file:
                becs = ananc_file.becs.values.tolist()
                e_electronic = ananc_file.emacro.cartesian_tensor.tolist()
                e_total = ananc_file.emacro_rlx.cartesian_tensor.tolist()

            data = {"ph_dos": complete_dos.as_dict(),
                    "ph_bs": symm_line_bands.as_dict(),
                    "becs": becs,
                    "e_electronic": e_electronic,
                    "e_total": e_total}

            return data

    def get_sum_rule_breakings(self, item):
        """
        Extracts the breaking of the acoustic and charge neutrality sum rules.
        Runs anaddb to get the values.
        """
        structure = Structure.from_dict(item["abinit_input"]["structure"])
        anaddb_input = AnaddbInput.modes_at_qpoint(structure, [0,0,0], asr=0, chneut=0)

        with tempfile.TemporaryDirectory() as workdir:
            task = self.run_anaddb(item["ddb_path"], anaddb_input, workdir)

            with AnaddbNcFile(os.path.join(workdir, "anaddb.nc")) as ananc_file:
                becs = ananc_file.becs

            with task.open_phbst() as phbst_file:
                phbands = phbst_file.phbands

            # If the ASR breaking could not be identified. set it to None to signal the
            # missing information. This may trigger a warning.
            try:
                asr_breaking = phbands.asr_breaking(units='cm-1', threshold=0.9, raise_on_no_indices=True)
            except RuntimeError as e:
                self.logger.warning("Could not find the ASR breaking for {}".format(item["mp_id"]))
                asr_breaking = None

            breakings = {"cnsr": np.max(np.abs(becs.sumrule)), "asr": asr_breaking.absmax_break}

        return breakings

    def get_warnings(self, asr_break, cnsr_break, ph_bs):
        """

        Args:
            asr_break (float): the largest breaking of the acoustic sum rule in cm^-1
            cnsr_break (float): the largest breaking of the charge neutrality sum rule
            ph_bs (dict): the dict of the PhononBandStructure
        """

        warnings = {}

        warnings['large_asr_break'] = asr_break > 30
        warnings['large_cnsr_break'] = cnsr_break > 0.2

        # neglect small negative frequencies (0.03 THz ~ 1 cm^-1)
        limit = -0.03

        bands = np.array(ph_bs['bands'])
        neg_freq = bands < limit

        has_neg_freq = np.any(neg_freq)

        warnings['has_neg_fr'] = has_neg_freq

        warnings['small_q_neg_fr'] = False
        if has_neg_freq:
            qpoints = np.array(ph_bs['qpoints'])

            qpt_has_neg_freq = np.any(neg_freq, axis=0)

            if np.max(np.linalg.norm(qpoints[qpt_has_neg_freq], axis=1)) < 0.05:
                warnings['small_q_neg_fr'] = True

        return warnings

    def run_anaddb(self, ddb_path, anaddb_input, workdir):
        """
        Runs anaddb. Raise AnaddbError if the calculation couldn't complete

        Args:
            ddb_path (str): path to the DDB file
            anaddb_input (AnaddbInput): the input for anaddb
            workdir (str): the directory where the calculation is run
        Returns:
            An abipy AnaddbTask instance.
        """

        task = AnaddbTask.temp_shell_task(anaddb_input, ddb_node=ddb_path, workdir=workdir, manager=self.manager)

        # Run the task here.
        task.start_and_wait(autoparal=False)

        report = task.get_event_report()
        if not report.run_completed:
            raise AnaddbError(task=task, report=report)

        return task


    def get_properties_anaddb_input(self, item):
        """
        creates the AnaddbInput object to calculate the phonon properties.
        It also returns the list of qpoints labels for generating the PhononBandStructureSymmLine.
        """

        ngqpt = item["abinit_input"]["ngqpt"]
        q1shft = [(0, 0, 0)]

        structure = Structure.from_dict(item["abinit_input"]["structure"])

        hs = HighSymmKpath(structure, symprec=1e-2)

        spgn = hs._sym.get_space_group_number()
        if spgn != item["spacegroup"]["number"]:
            raise RuntimeError("Parsed specegroup number {} does not match "
                               "calculation spacegroup {}".format(spgn, item["spacegroup"]["number"]))

        # for the moment use gaussian smearing
        prtdos = 1
        dossmear = 3 / Ha_cmm1
        lo_to_splitting = True
        dipdip = 1
        asr = 2
        chneut = 1
        ng2qppa = 500000

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

        # Parameters for dielectric constant
        inp['dieflag'] = 1

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
            phbands (PhononBands): the phonon band structures
            labels_list (list): list of labels used to generate the path
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

    def abinit_input_vars(self, item):
        """
        Extracts the useful abinit input parameters from an item.
        """

        i = item['abinit_input']

        data = {}

        data['ngqpt'] = i['ngqpt']
        data['ngkpt'] = i['ngkpt']
        data['shiftk'] = i['shiftk']
        data['ecut'] = i['ecut']
        data['occopt'] = i['occopt']
        data['tsmear'] = i.get('tsmear', 0)

        return data

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([[dict]]): a list of list of phonon dictionaries to update
        """
        items = list(filter(None, items))
        items_ph_band = [{self.phonon_bs.key: i[self.phonon.key],
                          "ph_bs": i['phonon'].pop('ph_bs')} for i in items]
        items_ddb = [{self.ddb_files.key: i[self.phonon.key],
                      "ddb_str": i.pop('ddb_str')} for i in items]

        if len(items) > 0:
            self.logger.info("Updating {} phonon docs".format(len(items)))
            self.phonon.update(docs=items)
            self.phonon_bs.update(docs=items_ph_band)
            self.ddb_files.update(docs=items_ddb)
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
        self.phonon.ensure_index(self.phonon.key, unique=True)
        self.phonon.ensure_index(self.phonon_bs.key, unique=True)
        self.phonon.ensure_index(self.ddb_files.key, unique=True)
