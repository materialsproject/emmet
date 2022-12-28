import tempfile
import os
from emmet.builders.settings import EmmetBuildSettings
import numpy as np
from typing import Optional, Dict, List, Iterator, Tuple

from pymatgen.phonon.bandstructure import PhononBandStructureSymmLine
from pymatgen.phonon.dos import CompletePhononDos
from pymatgen.phonon.ir_spectra import IRDielectricTensor
from pymatgen.core.structure import Structure
from pymatgen.io.abinit.abiobjects import KSampling
from pymatgen.symmetry.bandstructure import HighSymmKpath
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from abipy.dfpt.anaddbnc import AnaddbNcFile
from abipy.abio.inputs import AnaddbInput
from abipy.flowtk.tasks import AnaddbTask, TaskManager
from abipy.dfpt.ddb import AnaddbError, DielectricTensorGenerator, DdbFile
from abipy.dfpt.phonons import PhononBands
from abipy.core.abinit_units import eV_to_THz
from maggma.builders import Builder
from maggma.core import Store

from emmet.core.phonon import PhononWarnings, ThermodynamicProperties, AbinitPhonon, VibrationalEnergy
from emmet.core.phonon import PhononDos, PhononBandStructure, PhononWebsiteBS, Ddb, ThermalDisplacement
from emmet.core.polar import DielectricDoc, BornEffectiveCharges, IRDielectric
from emmet.core.utils import jsanitize

SETTINGS = EmmetBuildSettings()


class PhononBuilder(Builder):
    def __init__(
        self,
        phonon_materials: Store,
        ddb_source: Store,
        phonon: Store,
        phonon_bs: Store,
        phonon_dos: Store,
        ddb_files: Store,
        th_disp: Store,
        phonon_website: Store,
        query: Optional[Dict] = None,
        manager: Optional[TaskManager] = None,
        symprec: float = SETTINGS.SYMPREC,
        angle_tolerance: float = SETTINGS.ANGLE_TOL,
        chunk_size=100,
        **kwargs,
    ):
        """
        Creates a set of collections for materials generating different kind of data
        from the phonon calculations.
        The builder requires the execution of the anaddb tool available in abinit.
        The parts that may contain large amount of data are split from the main
        document and store in separated collections. Notice that in these cases
        the size of a single document may be above the 16MB limit allowed by the
        standard MongoDB document.

        Args:
            materials (Store): source Store of materials documents.
            ddb_source (Store): source Store of ddb files. Matching the data in the materials Store.
            phonon (Store): target Store of the phonon properties
            phonon_bs (Store): target Store for the phonon band structure. The document may
                exceed the 16MB limit of a mongodb collection.
            phonon_dos (Store): target Store for the phonon DOS. The document may
                exceed the 16MB limit of a mongodb collection.
            ddb_files (Store): target Store of the DDB files. The document may
                exceed the 16MB limit of a mongodb collection.
            th_disp (Store): target Store of the data related to the generalized phonon DOS
                with the mean square displacement tensor. The document may exceed the 16MB
                limit of a mongodb collection.
            phonon_website (Store): target Store for the phonon band structure in the phononwebsite
                format. The document may exceed the 16MB limit of a mongodb collection.
            query (dict): dictionary to limit materials to be analyzed
            manager (TaskManager): an instance of the abipy TaskManager. If None it
                will be generated from user configuration.
            symprec (float): tolerance for symmetry finding when determining the
                band structure path.
            angle_tolerance (float): angle tolerance for symmetry finding when
                determining the band structure path.
        """

        self.phonon_materials = phonon_materials
        self.phonon = phonon
        self.ddb_source = ddb_source
        self.phonon_bs = phonon_bs
        self.phonon_dos = phonon_dos
        self.ddb_files = ddb_files
        self.th_disp = th_disp
        self.phonon_website = phonon_website
        self.query = query or {}
        self.symprec = symprec
        self.angle_tolerance = angle_tolerance
        self.chunk_size = chunk_size

        if manager is None:
            self.manager = TaskManager.from_user_config()
        else:
            self.manager = manager

        super().__init__(
            sources=[phonon_materials, ddb_source],
            targets=[phonon, phonon_bs, phonon_dos, ddb_files, th_disp, phonon_website],
            chunk_size=chunk_size,
            **kwargs,
        )

    def get_items(self) -> Iterator[Dict]:
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

        mats = self.phonon.newer_in(self.phonon_materials, exhaustive=True, criteria=q)
        self.logger.info("Found {} new materials for phonon data".format(len(mats)))

        # list of properties queried from the results DB
        # basic information
        projection = {
            "mp_id": 1,
            "spacegroup.number": 1,
            "abinit_input": 1,  # input data
            "abinit_output.ddb_id": 1,  # file ids to be fetched
        }

        for m in mats:
            item = self.phonon_materials.query_one(properties=projection, criteria={self.phonon_materials.key: m})

            # Read the DDB file and pass as an object. Do not write here since in case of parallel
            # execution each worker will write its own file.
            ddb_data = self.ddb_source.query_one(criteria={"_id": item["abinit_output"]["ddb_id"]})
            if not ddb_data:
                self.logger.warning(f"DDB file not found for file id {item['abinit_output']['ddb_id']}")
                continue

            try:
                item["ddb_str"] = ddb_data["data"].decode("utf-8")
            except Exception:
                self.logger.warning(f"could not extract DDB for file id {item['abinit_output']['ddb_id']}")
                continue

            yield item

    def process_item(self, item: Dict) -> Optional[Dict]:
        """
        Generates the full phonon document from an item

        Args:
            item (dict): a dict extracted from the phonon calculations results.

        Returns:
            dict: a dict with the set of phonon data to be saved in the stores.
        """
        self.logger.debug("Processing phonon item for {}".format(item["mp_id"]))

        try:

            structure = Structure.from_dict(item["abinit_input"]["structure"])

            abinit_input_vars = self.abinit_input_vars(item)
            phonon_properties = self.get_phonon_properties(item)
            sr_break = self.get_sum_rule_breakings(item)
            ph_warnings = get_warnings(sr_break["asr"], sr_break["cnsr"], phonon_properties["ph_bs"])
            if PhononWarnings.NEG_FREQ not in ph_warnings:
                thermodynamic, vibrational_energy = get_thermodynamic_properties(phonon_properties["ph_dos"])
            else:
                thermodynamic, vibrational_energy = None, None

            becs = None
            if phonon_properties["becs"] is not None:
                becs = BornEffectiveCharges(
                    material_id=item["mp_id"],
                    symmetrized_value=phonon_properties["becs"],
                    value=sr_break["becs_nosymm"],
                    cnsr_break=sr_break["cnsr"],
                )

            ap = AbinitPhonon.from_structure(
                structure=structure,
                meta_structure=structure,
                include_structure=True,
                material_id=item["mp_id"],
                cnsr_break=sr_break["cnsr"],
                asr_break=sr_break["asr"],
                warnings=ph_warnings,
                dielectric=phonon_properties["dielectric"],
                becs=becs,
                ir_spectra=phonon_properties["ir_spectra"],
                thermodynamic=thermodynamic,
                vibrational_energy=vibrational_energy,
                abinit_input_vars=abinit_input_vars,
            )

            phbs = PhononBandStructure(material_id=item["mp_id"], band_structure=phonon_properties["ph_bs"].as_dict())

            phws = PhononWebsiteBS(
                material_id=item["mp_id"], phononwebsite=phonon_properties["ph_bs"].as_phononwebsite()
            )

            phdos = PhononDos(
                material_id=item["mp_id"],
                dos=phonon_properties["ph_dos"].as_dict(),
                dos_method=phonon_properties["ph_dos_method"],
            )

            ddb = Ddb(material_id=item["mp_id"], ddb=item["ddb_str"],)

            th_disp = ThermalDisplacement(
                material_id=item["mp_id"],
                structure=structure,
                nsites=len(structure),
                nomega=phonon_properties["th_disp"]["nomega"],
                ntemp=phonon_properties["th_disp"]["ntemp"],
                temperatures=phonon_properties["th_disp"]["tmesh"].tolist(),
                frequencies=phonon_properties["th_disp"]["wmesh"].tolist(),
                gdos_aijw=phonon_properties["th_disp"]["gdos_aijw"].tolist(),
                amu=phonon_properties["th_disp"]["amu_symbol"],
                ucif_t=phonon_properties["th_disp"]["ucif_t"].tolist(),
                ucif_string_t300k=phonon_properties["th_disp"]["ucif_string_t300k"],
            )

            self.logger.debug("Item generated for {}".format(item["mp_id"]))

            d = dict(
                abiph=jsanitize(ap.dict(), allow_bson=True),
                phbs=jsanitize(phbs.dict(), allow_bson=True),
                phws=jsanitize(phws.dict(), allow_bson=True),
                phdos=jsanitize(phdos.dict(), allow_bson=True),
                ddb=jsanitize(ddb.dict(), allow_bson=True),
                th_disp=jsanitize(th_disp.dict(), allow_bson=True),
            )

            return d
        except Exception as error:
            self.logger.warning("Error generating the phonon properties for {}: {}".format(item["mp_id"], error))
            return None

    def get_phonon_properties(self, item: Dict) -> Dict:
        """
        Extracts the phonon properties from the item
        """

        # the temp dir should still exist when using the objects as some readings are done lazily
        with tempfile.TemporaryDirectory() as workdir:

            structure = Structure.from_dict(item["abinit_input"]["structure"])

            self.logger.debug("Running anaddb in {}".format(workdir))

            ddb_path = os.path.join(workdir, "{}_DDB".format(item["mp_id"]))
            with open(ddb_path, "wt") as ddb_file:
                ddb_file.write(item["ddb_str"])

            ddb = DdbFile.from_string(item["ddb_str"])
            has_bec = ddb.has_bec_terms()
            has_epsinf = ddb.has_epsinf_terms()

            anaddb_input, labels_list = self.get_properties_anaddb_input(
                item, bs=True, dos="tetra", lo_to_splitting=has_bec, use_dieflag=has_epsinf
            )
            task = self.run_anaddb(ddb_path=ddb_path, anaddb_input=anaddb_input, workdir=workdir,)

            with task.open_phbst() as phbst_file, AnaddbNcFile(task.outpath_from_ext("anaddb.nc")) as ananc_file:
                # phbst
                phbands = phbst_file.phbands
                if has_bec:
                    phbands.read_non_anal_from_file(phbst_file.filepath)
                symm_line_bands = self.get_pmg_bs(phbands, labels_list)  # type: ignore

                # ananc
                if has_bec and ananc_file.becs is not None:
                    becs = ananc_file.becs.values.tolist()
                else:
                    becs = None
                if has_epsinf and ananc_file.epsinf is not None:
                    e_electronic = ananc_file.epsinf.tolist()
                else:
                    e_electronic = None
                e_total = ananc_file.eps0.tolist() if ananc_file.eps0 is not None else None
                if e_electronic and e_total:
                    e_ionic = (ananc_file.eps0 - ananc_file.epsinf).tolist()
                    dielectric = DielectricDoc.from_ionic_and_electronic(
                        ionic=e_ionic,
                        electronic=e_electronic,
                        material_id=item["mp_id"],
                        structure=structure,
                        deprecated=False,
                    )
                else:
                    dielectric = None

                # both
                if e_electronic and e_total and ananc_file.oscillator_strength is not None:
                    die_gen = DielectricTensorGenerator.from_objects(phbands, ananc_file)

                    ir_tensor = IRDielectricTensor(
                        die_gen.oscillator_strength, die_gen.phfreqs, die_gen.epsinf, die_gen.structure
                    ).as_dict()
                    ir_spectra = IRDielectric(ir_dielectric_tensor=ir_tensor)
                else:
                    ir_spectra = None

            dos_method = "tetrahedron"
            with task.open_phdos() as phdos_file:
                complete_dos = phdos_file.to_pymatgen()
                msqd_dos = phdos_file.msqd_dos

                # if the integrated dos is not close enough to the expected value (3*N_sites) rerun the DOS using
                # gaussian integration
                integrated_dos = phdos_file.phdos.integral()[-1][1]
                nmodes = 3 * len(phdos_file.structure)

            if np.abs(integrated_dos - nmodes) / nmodes > 0.01:
                self.logger.warning(
                    "Integrated DOS {} instead of {} for {}. Recalculating with gaussian".format(
                        integrated_dos, nmodes, item["mp_id"]
                    )
                )
                with tempfile.TemporaryDirectory() as workdir_dos:
                    anaddb_input_dos, _ = self.get_properties_anaddb_input(
                        item, bs=False, dos="gauss", lo_to_splitting=has_bec, use_dieflag=has_epsinf
                    )
                    task_dos = self.run_anaddb(ddb_path=ddb_path, anaddb_input=anaddb_input_dos, workdir=workdir_dos)
                    with task_dos.open_phdos() as phdos_file:
                        complete_dos = phdos_file.to_pymatgen()
                        msqd_dos = phdos_file.msqd_dos
                dos_method = "gaussian"

            data = {
                "ph_dos": complete_dos,
                "ph_dos_method": dos_method,
                "ph_bs": symm_line_bands,
                "becs": becs,
                "ir_spectra": ir_spectra,
                "dielectric": dielectric,
                "th_disp": msqd_dos.get_json_doc(tstart=0, tstop=800, num=161),
            }

            return data

    def get_sum_rule_breakings(self, item: dict) -> dict:
        """
        Extracts the breaking of the acoustic and charge neutrality sum rules.
        Runs anaddb to get the values.
        """
        structure = Structure.from_dict(item["abinit_input"]["structure"])
        anaddb_input = AnaddbInput.modes_at_qpoint(structure, [0, 0, 0], asr=0, chneut=0)

        with tempfile.TemporaryDirectory() as workdir:

            ddb_path = os.path.join(workdir, "{}_DDB".format(item["mp_id"]))
            with open(ddb_path, "wt") as ddb_file:
                ddb_file.write(item["ddb_str"])

            ddb = DdbFile.from_string(item["ddb_str"])
            has_bec = ddb.has_bec_terms()

            task = self.run_anaddb(ddb_path, anaddb_input, workdir)

            if has_bec:
                with AnaddbNcFile(task.outpath_from_ext("anaddb.nc")) as ananc_file:
                    becs = ananc_file.becs
                    becs_val = becs.values.tolist() if becs else None
                    cnsr = np.max(np.abs(becs.sumrule)) if becs else None
            else:
                becs_val = None
                cnsr = None

            with task.open_phbst() as phbst_file:
                phbands = phbst_file.phbands

            # If the ASR breaking could not be identified. set it to None to signal the
            # missing information. This may trigger a warning.
            try:
                asr_breaking = phbands.asr_breaking(units="cm-1", threshold=0.9, raise_on_no_indices=True)
                asr = asr_breaking.absmax_break
            except RuntimeError as e:
                self.logger.warning("Could not find the ASR breaking for {}. Error: {}".format(item["mp_id"], e))
                asr = None

            breakings = {"cnsr": cnsr, "asr": asr, "becs_nosymm": becs_val}

        return breakings

    def run_anaddb(self, ddb_path: str, anaddb_input: AnaddbInput, workdir: str) -> AnaddbTask:
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

    def get_properties_anaddb_input(
        self, item: dict, bs: bool = True, dos: str = "tetra", lo_to_splitting: bool = True, use_dieflag: bool = True
    ) -> Tuple[AnaddbInput, Optional[List]]:
        """
        creates the AnaddbInput object to calculate the phonon properties.
        It also returns the list of qpoints labels for generating the PhononBandStructureSymmLine.

        Args:
            item: the item to process
            bs (bool): if True the phonon band structure will be calculated
            dos (str): if 'tetra' the DOS will be calculated with the tetrahedron method,
                if 'gauss' with gaussian smearing, if None the DOS will not be calculated
            lo_to_splitting (bool): contributions from the LO-TO splitting for the phonon
                BS will be calculated.
            use_dieflag (bool): the dielectric tensor will be calculated.
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
            ifcflag=1, ngqpt=np.array(ngqpt), q1shft=q1shft, nqshft=len(q1shft), asr=asr, chneut=chneut, dipdip=dipdip,
        )

        # Parameters for the dos.
        if dos == "tetra":
            # Use tetrahedra with dense dosdeltae (required to get accurate value of the integral)
            prtdos = 2
            dosdeltae = 9e-07  # Ha = 2 cm^-1
            ng2qppa = 200000
            ng2qpt = KSampling.automatic_density(structure, kppa=ng2qppa).kpts[0]
            inp.set_vars(prtdos=prtdos, dosdeltae=dosdeltae, ng2qpt=ng2qpt)
        elif dos == "gauss":
            # Use gauss with denser grid and a smearing
            prtdos = 1
            dosdeltae = 4.5e-06  # Ha = 10 cm^-1
            ng2qppa = 500000
            dossmear = 1.82e-5  # Ha = 4 cm^-1
            ng2qpt = KSampling.automatic_density(structure, kppa=ng2qppa).kpts[0]
            inp.set_vars(prtdos=prtdos, dosdeltae=dosdeltae, dossmear=dossmear, ng2qpt=ng2qpt)
        elif dos is not None:
            raise ValueError("Unsupported value of dos.")

        # Parameters for the BS
        labels_list = None
        if bs:
            spga = SpacegroupAnalyzer(structure, symprec=self.symprec, angle_tolerance=self.angle_tolerance)

            spgn = spga.get_space_group_number()
            if spgn != item["spacegroup"]["number"]:
                raise RuntimeError(
                    "Parsed specegroup number {} does not match "
                    "calculation spacegroup {}".format(spgn, item["spacegroup"]["number"])
                )

            hs = HighSymmKpath(structure, symprec=self.symprec, angle_tolerance=self.angle_tolerance)

            qpts, labels_list = hs.get_kpoints(line_density=18, coords_are_cartesian=False)

            n_qpoints = len(qpts)
            qph1l = np.zeros((n_qpoints, 4))

            qph1l[:, :-1] = qpts
            qph1l[:, -1] = 1

            inp["qph1l"] = qph1l.tolist()
            inp["nph1l"] = n_qpoints

            if lo_to_splitting:
                kpath = hs.kpath
                directions = []  # type: list
                for qptbounds in kpath["path"]:
                    for i, qpt in enumerate(qptbounds):
                        if np.array_equal(kpath["kpoints"][qpt], (0, 0, 0)):
                            # anaddb expects cartesian coordinates for the qph2l list
                            if i > 0:
                                directions.extend(
                                    structure.lattice.reciprocal_lattice_crystallographic.get_cartesian_coords(
                                        kpath["kpoints"][qptbounds[i - 1]]
                                    )
                                )
                                directions.append(0)

                            if i < len(qptbounds) - 1:
                                directions.extend(
                                    structure.lattice.reciprocal_lattice_crystallographic.get_cartesian_coords(
                                        kpath["kpoints"][qptbounds[i + 1]]
                                    )
                                )
                                directions.append(0)

                if directions:
                    directions = np.reshape(directions, (-1, 4))  # type: ignore
                    inp.set_vars(nph2l=len(directions), qph2l=directions)

        # Parameters for dielectric constant
        if use_dieflag:
            inp["dieflag"] = 1

        return inp, labels_list

    @staticmethod
    def get_pmg_bs(phbands: PhononBands, labels_list: List) -> PhononBandStructureSymmLine:
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
                if phbands.non_anal_ph and "Gamma" in l:
                    if i > 0 and not labels_list[i - 1]:
                        ph_freqs[i] = phbands._get_non_anal_freqs(qpts[i - 1])
                        displ[i] = phbands._get_non_anal_phdispl(qpts[i - 1])
                    if i < len(qpts) - 1 and not labels_list[i + 1]:
                        ph_freqs[i] = phbands._get_non_anal_freqs(qpts[i + 1])
                        displ[i] = phbands._get_non_anal_phdispl(qpts[i + 1])

        ph_freqs = np.transpose(ph_freqs) * eV_to_THz
        displ = np.transpose(np.reshape(displ, (len(qpts), 3 * n_at, n_at, 3)), (1, 0, 2, 3))

        ph_bs_sl = PhononBandStructureSymmLine(
            qpoints=qpts,
            frequencies=ph_freqs,
            lattice=structure.reciprocal_lattice,
            has_nac=phbands.non_anal_ph is not None,
            eigendisplacements=displ,
            labels_dict=labels_dict,
            structure=structure,
        )

        ph_bs_sl.band_reorder()

        return ph_bs_sl

    @staticmethod
    def abinit_input_vars(item: dict) -> dict:
        """
        Extracts the useful abinit input parameters from an item.
        """

        i = item["abinit_input"]

        data = {}

        def get_vars(label):
            if label in i and i[label]:
                return {k: v for (k, v) in i[label]["abi_args"]}
            else:
                return {}

        data["gs_input"] = get_vars("gs_input")
        data["ddk_input"] = get_vars("ddk_input")
        data["dde_input"] = get_vars("dde_input")
        data["phonon_input"] = get_vars("phonon_input")
        data["wfq_input"] = get_vars("wfq_input")

        data["ngqpt"] = i["ngqpt"]
        data["ngkpt"] = i["ngkpt"]
        data["shiftk"] = i["shiftk"]
        data["ecut"] = i["ecut"]
        data["occopt"] = i["occopt"]
        data["tsmear"] = i.get("tsmear", 0)

        data["pseudopotentials"] = {
            "name": i["pseudopotentials"]["pseudos_name"],
            "md5": i["pseudopotentials"]["pseudos_md5"],
        }

        return data

    def update_targets(self, items: List[Dict]):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([dict]): a list of phonon dictionaries to update
        """
        items = list(filter(None, items))
        items_ph = [i["abiph"] for i in items]
        items_ph_band = [i["phbs"] for i in items]
        items_ph_dos = [i["phdos"] for i in items]
        items_ddb = [i["ddb"] for i in items]
        items_th_disp = [i["th_disp"] for i in items]
        items_ph_web = [i["phws"] for i in items]

        if len(items) > 0:
            self.logger.info("Updating {} phonon docs".format(len(items)))
            self.phonon.update(docs=items_ph)
            self.phonon_bs.update(docs=items_ph_band)
            self.phonon_dos.update(docs=items_ph_dos)
            self.ddb_files.update(docs=items_ddb)
            self.th_disp.update(docs=items_th_disp)
            self.phonon_website.update(docs=items_ph_web)

        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections
        """
        self.phonon_materials.ensure_index(self.phonon_materials.key, unique=True)

        self.phonon.ensure_index(self.phonon.key, unique=True)
        self.phonon_bs.ensure_index(self.phonon.key, unique=True)
        self.phonon_dos.ensure_index(self.phonon.key, unique=True)
        self.ddb_files.ensure_index(self.phonon.key, unique=True)
        self.th_disp.ensure_index(self.phonon.key, unique=True)
        self.phonon_website.ensure_index(self.phonon.key, unique=True)


def get_warnings(asr_break: float, cnsr_break: float, ph_bs: PhononBandStructureSymmLine) -> List[PhononWarnings]:
    """

    Args:
        asr_break (float): the largest breaking of the acoustic sum rule in cm^-1
        cnsr_break (float): the largest breaking of the charge neutrality sum rule
        ph_bs (PhononBandStructureSymmLine): the phonon band structure

    Returns:
        PhononWarnings: the model containing the data of the warnings.
    """

    warnings = []

    if asr_break and asr_break > 30:
        warnings.append(PhononWarnings.ASR)
    if cnsr_break and cnsr_break > 0.2:
        warnings.append(PhononWarnings.CNSR)

    # neglect small negative frequencies (0.03 THz ~ 1 cm^-1)
    limit = -0.03

    bands = np.array(ph_bs.bands)
    neg_freq = bands < limit

    # there are negative frequencies anywhere in the BZ
    if np.any(neg_freq):
        warnings.append(PhononWarnings.NEG_FREQ)

        qpoints = np.array([q.frac_coords for q in ph_bs.qpoints])

        qpt_has_neg_freq = np.any(neg_freq, axis=0)

        if np.max(np.linalg.norm(qpoints[qpt_has_neg_freq], axis=1)) < 0.05:
            warnings.append(PhononWarnings.SMALL_Q_NEG_FREQ)

    return warnings


def get_thermodynamic_properties(ph_dos: CompletePhononDos) -> Tuple[ThermodynamicProperties, VibrationalEnergy]:
    """
    Calculates the thermodynamic properties from a phonon DOS

    Args:
        ph_dos (CompletePhononDos): The DOS used to calculate the properties.

    Returns:
        ThermodynamicProperties and VibrationalEnergy: the models containing the calculated thermodynamic
            properties and vibrational contribution to the total energy.
    """

    tstart, tstop, nt = 0, 800, 161
    temp = np.linspace(tstart, tstop, nt)

    cv = []
    entropy = []
    internal_energy = []
    helmholtz_free_energy = []

    for t in temp:
        cv.append(ph_dos.cv(t, ph_dos.structure))
        entropy.append(ph_dos.entropy(t, ph_dos.structure))
        internal_energy.append(ph_dos.internal_energy(t, ph_dos.structure))
        helmholtz_free_energy.append(ph_dos.helmholtz_free_energy(t, ph_dos.structure))

    zpe = ph_dos.zero_point_energy(ph_dos.structure)

    temperatures = temp.tolist()
    tp = ThermodynamicProperties(temperatures=temperatures, cv=cv, entropy=entropy)

    ve = VibrationalEnergy(
        temperatures=temperatures,
        internal_energy=internal_energy,
        helmholtz_free_energy=helmholtz_free_energy,
        zero_point_energy=zpe,
    )

    return tp, ve
