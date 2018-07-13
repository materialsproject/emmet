import tempfile
import gridfs
import os

from abipy.dfpt.anaddbnc import AnaddbNcFile
from monty.json import jsanitize
from pymatgen.phonon.bandstructure import PhononBandStructureSymmLine
from pymatgen.core.structure import Structure
from pymatgen.io.abinit.abiobjects import KSampling
from pymatgen.symmetry.bandstructure import HighSymmKpath
import numpy as np
from abipy.abio.inputs import AnaddbInput
from abipy.flowtk.tasks import AnaddbTask, TaskManager
from abipy.dfpt.ddb import AnaddbError
from abipy.core.abinit_units import eV_to_THz

from maggma.builder import Builder


#TODO - handle possible other sources for the anaddb netcdf files?
#     - add input more parameters to tune anaddb calculation?
#     - store the anaddb netcdf output to speedup possible rerunning of the builder?


class PhononBuilder(Builder):
    def __init__(self, materials, phonon, phonon_bs, phonon_dos, ddb_files, query=None,
                 manager=None, tmp_ddb_dir=None, **kwargs):
        """
        Creates a phonon collection for materials.

        Args:
            materials (Store): source Store of materials documents
            phonon (Store): target Store of the phonon properties
            phonon_bs (Store): target Store for the phonon band structure. The document may
                exceed the 16MB limit of the mongodb collections.
            phonon_dos (Store): target Store for the phonon DOS. The document may
                exceed the 16MB limit of the mongodb collections.
            ddb_files (Store): target Store of the DDB files. The document may
                exceed the 16MB limit of the mongodb collections.
            query (dict): dictionary to limit materials to be analyzed
            manager (TaskManager): an instance of the abipy TaskManager. If None it will be
                generated from user configuration.
            tmp_ddb_dir (str): in case a parallel Processor is used over different nodes, the temporary
                DDB files should be in a directory accessible from all the nodes. If None a
                temporary directory will be created in the current folder.
        """

        self.materials = materials
        self.phonon = phonon
        self.phonon_bs = phonon_bs
        self.phonon_dos = phonon_dos
        self.ddb_files = ddb_files

        if query is None:
            query = {}
        self.query = query

        if manager is None:
            self.manager = TaskManager.from_user_config()
        else:
            self.manager = manager

        super().__init__(sources=[materials],
                         targets=[phonon, phonon_bs, phonon_dos, ddb_files],
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
        projection["abinit_input"] = 1
        # file ids to be fetched
        projection["abinit_output.ddb_id"] = 1

        # initialize the gridfs
        ddbfs = gridfs.GridFS(self.materials.collection.database, "ddb_fs")

        for m in mats:
            item = self.materials.query_one(properties=projection, criteria={self.materials.key: m[self.materials.key]})

            # Read the DDB file and pass as an object. Do not write here since in case of parallel
            # execution each worker will write its own file.
            item["ddb_str"] = ddbfs.get(item["abinit_output"]["ddb_id"]).read().decode('utf-8')

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

            ph_data = {"structure": structure.as_dict(), "ddb_str": item["ddb_str"]}
            ph_data["abinit_input_vars"] = self.abinit_input_vars(item)
            ph_data["phonon"] = self.get_phonon_properties(item)
            sr_break = self.get_sum_rule_breakings(item)
            ph_data["sum_rules_breaking"] = sr_break
            ph_data["warnings"] = get_warnings(sr_break["asr"], sr_break["cnsr"], ph_data["phonon"]["ph_bs"])
            ph_data[self.phonon.key] = item["mp_id"]

            self.logger.debug("Item generated for {}".format(item["mp_id"]))

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

            self.logger.debug("Running anaddb in {}".format(workdir))

            ddb_path = os.path.join(workdir, "{}_DDB".format(item["mp_id"]))
            with open(ddb_path, "wt") as ddb_file:
                ddb_file.write(item["ddb_str"])

            anaddb_input, labels_list = self.get_properties_anaddb_input(item, bs=True, dos='tetra')
            task = self.run_anaddb(ddb_path=ddb_path, anaddb_input=anaddb_input, workdir=workdir)

            with task.open_phbst() as phbst_file:
                phbands = phbst_file.phbands
                phbands.read_non_anal_from_file(phbst_file.filepath)
                symm_line_bands = self.get_pmg_bs(phbands, labels_list)

            with AnaddbNcFile(os.path.join(workdir, "anaddb.nc")) as ananc_file:
                becs = ananc_file.becs.values.tolist()
                e_electronic = ananc_file.emacro.cartesian_tensor.tolist()
                e_total = ananc_file.emacro_rlx.cartesian_tensor.tolist()

            dos_method = "tetrahedron"
            with task.open_phdos() as phdos_file:
                complete_dos = phdos_file.to_pymatgen()

                # if the integrated dos is not close enough to the expected value (3*N_sites) rerun the DOS using
                # gaussian integration
                integrated_dos = phdos_file.phdos.integral()[-1][1]
                nmodes = 3 * len(phdos_file.structure)

            if np.abs(integrated_dos - nmodes) / nmodes > 0.01:
                self.logger.warning("Integrated DOS {} instead of {} for {}. Recalculating with gaussian".format(integrated_dos, nmodes, item["mp_id"]))
                with tempfile.TemporaryDirectory() as workdir_dos:
                    anaddb_input_dos, _ = self.get_properties_anaddb_input(item, bs=False, dos='gauss')
                    task_dos = self.run_anaddb(ddb_path=ddb_path, anaddb_input=anaddb_input_dos, workdir=workdir_dos)
                    with task_dos.open_phdos() as phdos_file:
                        complete_dos = phdos_file.to_pymatgen()

                dos_method = "gaussian"

            data = {"ph_dos": complete_dos.as_dict(),
                    "ph_dos_method": dos_method,
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

            ddb_path = os.path.join(workdir, "{}_DDB".format(item["mp_id"]))
            with open(ddb_path, "wt") as ddb_file:
                ddb_file.write(item["ddb_str"])

            task = self.run_anaddb(ddb_path, anaddb_input, workdir)

            with AnaddbNcFile(os.path.join(workdir, "anaddb.nc")) as ananc_file:
                becs = ananc_file.becs

            with task.open_phbst() as phbst_file:
                phbands = phbst_file.phbands

            # If the ASR breaking could not be identified. set it to None to signal the
            # missing information. This may trigger a warning.
            try:
                asr_breaking = phbands.asr_breaking(units='cm-1', threshold=0.9, raise_on_no_indices=True)
            except RuntimeError as e:
                self.logger.warning("Could not find the ASR breaking for {}. Error: {}".format(item["mp_id"], e))
                asr_breaking = None

            breakings = {"cnsr": np.max(np.abs(becs.sumrule)), "asr": asr_breaking.absmax_break}

        return breakings

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
        self.logger.debug("Start anaddb for {}".format(ddb_path))
        task.start_and_wait(autoparal=False)
        self.logger.debug("Finished anaddb for {}".format(ddb_path))

        report = task.get_event_report()
        if not report.run_completed:
            raise AnaddbError(task=task, report=report)

        self.logger.debug("anaddb succesful for {}".format(ddb_path))

        return task


    def get_properties_anaddb_input(self, item, bs=True, dos='tetra', lo_to_splitting=True):
        """
        creates the AnaddbInput object to calculate the phonon properties.
        It also returns the list of qpoints labels for generating the PhononBandStructureSymmLine.

        Args:
            item: the item to process
            bs (bool): if True the phonon band structure will be calculated
            dos (str): if 'tetra' the DOS will be calculated with the tetrahedron method, if 'gauss' with gaussian
                smearing, if None the DOS will not be calculated
            lo_to_splitting (bool): contributions from the LO-TO splitting for the phonon BS will be calculated.
        """

        ngqpt = item["abinit_input"]["ngqpt"]
        q1shft = [(0, 0, 0)]

        structure = Structure.from_dict(item["abinit_input"]["structure"])

        # use all the corrections
        dipdip = 1
        asr = 2
        chneut = 1

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
        if dos == 'tetra':
            # Use tetrahedra with dense dosdeltae (required to get accurate value of the integral)
            prtdos = 2
            dosdeltae = 9e-07 # Ha = 2 cm^-1
            ng2qppa = 1000
            ng2qpt = KSampling.automatic_density(structure, kppa=ng2qppa).kpts[0]
            inp.set_vars(prtdos=prtdos, dosdeltae=dosdeltae, ng2qpt=ng2qpt)
        elif dos == 'gauss':
            # Use gauss with denser grid and a smearing
            prtdos = 1
            dosdeltae = 4.5e-06 # Ha = 10 cm^-1
            ng2qppa = 1000
            dossmear = 1.82e-5 # Ha = 4 cm^-1
            ng2qpt = KSampling.automatic_density(structure, kppa=ng2qppa).kpts[0]
            inp.set_vars(prtdos=prtdos, dosdeltae=dosdeltae, dossmear=dossmear, ng2qpt=ng2qpt)
        elif dos is not None:
            raise ValueError("Unsupported value of dos.")

        # Parameters for the BS
        labels_list = None
        if bs:
            hs = HighSymmKpath(structure, symprec=1e-2)

            spgn = hs._sym.get_space_group_number()
            if spgn != item["spacegroup"]["number"]:
                raise RuntimeError("Parsed specegroup number {} does not match "
                                   "calculation spacegroup {}".format(spgn, item["spacegroup"]["number"]))

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
                                directions.extend(
                                    structure.lattice.reciprocal_lattice_crystallographic.get_cartesian_coords(
                                        kpath['kpoints'][qptbounds[i - 1]]))
                                directions.append(0)

                            if i < len(qptbounds) - 1:
                                directions.extend(
                                    structure.lattice.reciprocal_lattice_crystallographic.get_cartesian_coords(
                                        kpath['kpoints'][qptbounds[i + 1]]))
                                directions.append(0)

                if directions:
                    directions = np.reshape(directions, (-1, 4))
                    inp.set_vars(
                        nph2l=len(directions),
                        qph2l=directions
                    )

        # Parameters for dielectric constant
        inp['dieflag'] = 1

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

        ph_freqs = np.transpose(ph_freqs) * eV_to_THz
        displ = np.transpose(np.reshape(displ, (len(qpts), 3*n_at, n_at, 3)), (1, 0, 2, 3))

        ph_bs_sl = PhononBandStructureSymmLine(qpoints=qpts, frequencies=ph_freqs,
                                               lattice=structure.reciprocal_lattice,
                                               has_nac=phbands.non_anal_ph is not None, eigendisplacements=displ,
                                               labels_dict=labels_dict, structure=structure)

        ph_bs_sl.band_reorder()

        return ph_bs_sl

    def abinit_input_vars(self, item):
        """
        Extracts the useful abinit input parameters from an item.
        """

        i = item['abinit_input']

        data = {}

        def get_vars(label):
            if label in i and i[label]:
                return {k:v for (k,v) in i[label]['abi_args']}
            else:
                return {}

        data['gs_input'] = get_vars('gs_input')
        data['ddk_input'] = get_vars('ddk_input')
        data['dde_input'] = get_vars('dde_input')
        data['phonon_input'] = get_vars('phonon_input')
        data['wfq_input'] = get_vars('wfq_input')

        data['ngqpt'] = i['ngqpt']
        data['ngkpt'] = i['ngkpt']
        data['shiftk'] = i['shiftk']
        data['ecut'] = i['ecut']
        data['occopt'] = i['occopt']
        data['tsmear'] = i.get('tsmear', 0)

        data['pseudopotentials'] = {'name': i['pseudopotentials']['pseudos_name'],
                                    'md5': i['pseudopotentials']['pseudos_md5']}

        return data

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([[dict]]): a list of list of phonon dictionaries to update
        """
        self.logger.debug("Start update_targets")
        items = list(filter(None, items))
        items_ph_band = [{self.phonon_bs.key: i[self.phonon.key],
                          "ph_bs": i['phonon'].pop('ph_bs')} for i in items]
        items_ph_dos = [{self.phonon_dos.key: i[self.phonon.key],
                         "ph_dos": i['phonon'].pop('ph_dos')} for i in items]
        items_ddb = [{self.ddb_files.key: i[self.phonon.key],
                      "ddb_str": i.pop('ddb_str')} for i in items]

        if len(items) > 0:
            self.logger.info("Updating {} phonon docs".format(len(items)))
            self.phonon.update(docs=items)
            self.phonon_bs.update(docs=items_ph_band)
            self.phonon_dos.update(docs=items_ph_dos)
            self.ddb_files.update(docs=items_ddb)
        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections
        :return:
        """
        # Search index for materials
        # self.materials.ensure_index(self.materials.key, unique=True)

        # Search index for materials
        self.phonon.ensure_index(self.phonon.key, unique=True)
        self.phonon_bs.ensure_index(self.phonon_bs.key, unique=True)
        self.phonon_dos.ensure_index(self.phonon_dos.key, unique=True)
        self.ddb_files.ensure_index(self.ddb_files.key, unique=True)


def get_warnings(asr_break, cnsr_break, ph_bs):
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