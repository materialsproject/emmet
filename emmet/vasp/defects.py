"""
This module contains 2 builders for defect properties in non-metals.

1.  The DefectBuilder builds individual Defect documents
    with bulk and dielectric properties included, along
    with properties neccessary for accessing delocalization
    and parsing further defect thermodynamics.
2.  The DefectThermoBuilder builds DefectPhaseDiagram
    documents from defect objects with identical bulk structures
    and calculation metadata.
"""

from datetime import datetime
import numpy as np

from monty.json import MontyDecoder, jsanitize

from pymatgen import Structure, MPRester, PeriodicSite
from pymatgen.analysis.structure_matcher import StructureMatcher, PointDefectComparator
from pymatgen.electronic_structure.bandstructure import BandStructure
from pymatgen.analysis.defects.core import Vacancy, Substitution, Interstitial, DefectEntry
from pymatgen.analysis.defects.thermodynamics import DefectPhaseDiagram
from pymatgen.analysis.defects.defect_compatibility import DefectCompatibility

from maggma.builder import Builder


__author__ = "Danny Broberg, Shyam Dwaraknath"


class DefectBuilder(Builder):
    def __init__(self,
                 tasks,
                 defects,
                 query=None,
                 compatibility=DefectCompatibility(),
                 ltol=0.2,
                 stol=0.3,
                 angle_tol=5,
                 max_items_size=0,
                 update_all=False,
                 **kwargs):
        """
        Creates DefectEntry from vasp task docs

        Args:
            tasks (Store): Store of tasks documents
            defects (Store): Store of defect entries with all metadata required for followup decisions on defect thermo
            query (dict): dictionary to limit materials to be analyzed
            compatibility (DefectCompatability): Compatability module to ensure defect calculations are compatible
            ltol (float): StructureMatcher tuning parameter for matching tasks to materials
            stol (float): StructureMatcher tuning parameter for matching tasks to materials
            angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
            max_items_size (int): limits number of items approached from tasks (zero places no limit on number of items)
            update_all (bool): Whether to consider all task ids from defects store.
                Default is False (will not re-consider task-ids which have been considered previously.
        """

        self.tasks = tasks
        self.defects = defects
        self.query = query if query else {}
        self.compatibility = compatibility
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.max_items_size = max_items_size
        self.update_all=update_all
        super().__init__(sources=[tasks], targets=[defects], **kwargs)

    def get_items(self):
        """
        Gets sets of entries from chemical systems that need to be processed

        Returns:
            generator of relevant entries from one chemical system

        """
        self.logger.info("Defect Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indicies()

        # Save timestamp for update operation
        self.time_stamp = datetime.utcnow()

        # Get all successful defect tasks that have been updated since
        # defect_store was last updated
        q = dict(self.query)
        q["state"] = "successful"
        if not self.update_all:
            if 'task_id' in q:
                if isinstance(q['task_id'], int) or isinstance(q['task_id'], float):
                    q['task_id'] = {'$nin': [], '$in': [q['task_id']]}
                if '$nin' in q['task_id']:
                    q['task_id']['$nin'].extend( self.defects.distinct('entry_id'))
                else:
                    q['task_id'].update( {'$nin': self.defects.distinct('entry_id')})
            else:
                q.update({'task_id': {'$nin': self.defects.distinct('entry_id')}})

        q.update({'transformations.history.@module':
                      {'$in': ['pymatgen.transformations.defect_transformations']}})
        defect_tasks = list(self.tasks.query(criteria=q,
                                             properties=['task_id', 'transformations.history.0.defect.structure']))
        if self.max_items_size and len(defect_tasks) > self.max_items_size:
            defect_tasks = [dtask for dind, dtask in enumerate(defect_tasks) if dind < self.max_items_size]
        task_ids = [dtask['task_id'] for dtask in defect_tasks]
        self.logger.info("Found {} new defect tasks to consider:\n{}".format( len(defect_tasks), task_ids))

        # get a few other tasks which are needed for defect entries (regardless of when they were last updated):
        # bulk_supercell, dielectric calc, BS calc, HSE-BS calc
        bulksc = {"state": "successful", 'transformations.history.0.@module':
            {'$in': ['pymatgen.transformations.standard_transformations']}}
        dielq = {"state": "successful", "input.incar.LEPSILON": True, "input.incar.LPEAD": True}
        HSE_BSq = {"state": "successful", 'calcs_reversed.0.input.incar.LHFCALC': True,
                   'transformations.history.0.@module':
                        {'$nin': ['pymatgen.transformations.defect_transformations',
                                  'pymatgen.transformations.standard_transformations']}}
        # TODO: add smarter capability for getting HSE bandstructure from tasks
        # TODO: add capability for getting GGA bandstructure from tasks?

        # now load up all defect tasks with relevant information required for process_item step
        # includes querying bulk, diel and hybrid calcs as you go along.
        log_additional_tasks = dict() #to minimize number of bulk + diel + hse queries, log by chemsys

        needed_defect_properties = ['task_id', 'transformations', 'input',
                                    'task_label', 'last_updated',
                                    'output', 'calcs_reversed', 'chemsys']
        needed_bulk_properties = ['task_id', 'chemsys', 'task_label',
                                  'last_updated', 'transformations',
                                  'input', 'output', 'calcs_reversed']
        for d_task_id in task_ids:
            d_task = list(self.tasks.query(criteria={"task_id": d_task_id},
                                           properties=needed_defect_properties))[0]
            chemsys = "-".join(sorted((Structure.from_dict(
                d_task['transformations']['history'][0]['defect']['structure']).symbol_set)))

            if chemsys not in log_additional_tasks.keys():
                #grab all bulk calcs for chemsys
                q = bulksc.copy()
                q.update( {"chemsys": chemsys})
                bulk_tasks = list(self.tasks.query(criteria=q, properties=needed_bulk_properties))

                #grab all diel calcs for chemsys
                q = dielq.copy()
                q.update( {"chemsys": chemsys})
                diel_tasks = list(self.tasks.query(criteria=q,
                                                   properties=['task_id', 'task_label', 'last_updated',
                                                               'input', 'output']))

                #grab all hse bs calcs for chemsys
                q = HSE_BSq.copy()
                q.update( {"chemsys": chemsys})
                hybrid_tasks = list(self.tasks.query(criteria=q,
                                                     properties=['task_id', 'input',
                                                                 'output', 'task_label']))

                self.logger.debug("\t{} has {} bulk loaded {} diel and {} hse"
                                  "".format( chemsys, len(bulk_tasks),
                                             len(diel_tasks), len(hybrid_tasks)))

                log_additional_tasks.update({chemsys: {'bulksc': bulk_tasks[:],
                                                       'diel': diel_tasks[:],
                                                       'hsebs': hybrid_tasks[:]}})

            yield [d_task, log_additional_tasks[chemsys]]

    def process_item(self, item):
        """
        Process a defect item (containing defect, bulk and dielectric information as processed in get_items)

        Args:
            item (defect_task): a defect_task to process into a DefectEntry object

        Returns:
            dict: a DefectEntry dictionary to update defect database with
        """
        d_task, chemsys_additional_tasks = item

        defect_task = self.find_and_load_bulk_tasks(d_task, chemsys_additional_tasks)
        if defect_task is None:
            self.logger.error("Could not determine defect bulk properties for {}".format( d_task['task_id']))
            return
        elif 'bulk_task' not in defect_task.keys():
            self.logger.error("bulk_task is not in item! Cannot parse task id = {}.".format( d_task['task_id']))
            return
        elif 'diel_task_meta' not in defect_task.keys():
            self.logger.error("diel_task_meta is not in item! Cannot parse task id = {}.".format( d_task['task_id']))
            return

        #initialize parameters with dielectric data
        eps_ionic = defect_task['diel_task_meta']['epsilon_ionic']
        eps_static = defect_task['diel_task_meta']['epsilon_static']
        eps_total = []
        for i in range(3):
            eps_total.append([e[0]+e[1] for e in zip(eps_ionic[i], eps_static[i])])
        parameters = {'epsilon_ionic': eps_ionic, 'epsilon_static':  eps_static,
                      'dielectric': eps_total,
                      'task_level_metadata':
                          {'diel_taskdb_task_id': defect_task['diel_task_meta']['diel_taskdb_task_id']}}

        parameters = self.get_run_metadata( defect_task, parameters)

        # add bulk data to parameters
        bulk_task = defect_task['bulk_task']
        bulk_energy = bulk_task['output']['energy']
        bulk_sc_structure = Structure.from_dict( bulk_task['input']['structure'])
        parameters.update( {'bulk_energy': bulk_energy, 'bulk_sc_structure': bulk_sc_structure})

        parameters = self.get_bulk_gap_data( bulk_task, parameters)
        parameters = self.get_bulk_chg_correction_metadata( bulk_task, parameters)


        # Add defect data to parameters
        defect_energy = defect_task['output']['energy']
        parameters.update({'defect_energy': defect_energy})

        defect, parameters = self.load_defect_and_structure_data( defect_task, parameters)

        parameters = self.load_defect_chg_correction_metadata( defect, defect_task, parameters)

        if 'vr_eigenvalue_dict' in defect_task['calcs_reversed'][0]['output'].keys():
            eigenvalues = defect_task['calcs_reversed'][0]['output']['vr_eigenvalue_dict']['eigenvalues']
            kpoint_weights = defect_task['calcs_reversed'][0]['output']['vr_eigenvalue_dict']['kpoint_weights']
            parameters.update( {'eigenvalues': eigenvalues,
                                'kpoint_weights': kpoint_weights} )
        else:
            self.logger.error('DEFECTTYPEcalc: {} (task-id {}) does not have eigenvalue data for parsing '
                  'bandfilling.'.format(defect_task['task_label'], defect_task['task_id']))

        if 'defect' in defect_task['calcs_reversed'][0]['output'].keys():
            parameters.update( {'defect_ks_delocal_data':
                                    defect_task['calcs_reversed'][0]['output']['defect'].copy()})
        else:
            self.logger.error('DEFECTTYPEcalc: {} (task-id {}) does not have defect data for parsing '
                  'delocalization.'.format(defect_task['task_label'], defect_task['task_id']))

        defect_entry = DefectEntry( defect, parameters['defect_energy'] - parameters['bulk_energy'],
                                    corrections = {}, parameters = parameters, entry_id= defect_task['task_id'])

        defect_entry = self.compatibility.process_entry( defect_entry)
        defect_entry.parameters = jsanitize( defect_entry.parameters, strict=True, allow_bson=True)
        defect_entry_as_dict = defect_entry.as_dict()
        defect_entry_as_dict['task_id'] = defect_entry_as_dict['entry_id'] #this seemed neccessary for legacy db

        return defect_entry_as_dict

    def update_targets(self, items):
        """
        Inserts the defect docs into the defect collection

        Args:
            items ([dict]): a list of defect entries as dictionaries
        """
        items = [item for item in items if item]
        self.logger.info("Updating {} defect documents".format(len(items)))

        self.defects.update(items, update_lu=True, key='entry_id')

    def ensure_indicies(self):
        """
        Ensures indicies on the tasks and defects collections
        :return:
        """
        # Search indicies for tasks
        self.tasks.ensure_index(self.tasks.key, unique=True)
        self.tasks.ensure_index("chemsys")

        # Search indicies for defects
        self.defects.ensure_index(self.defects.key, unique=True)
        self.defects.ensure_index("chemsys")

    def find_and_load_bulk_tasks(self, defect_task, additional_tasks):
        """
        This takes defect_task and finds bulk task, diel task, and other things as appropriate (example hse_data...)

        needs to make sure INCAR settings and structure matching works for all

        :param defect_task:
        :param additional_tasks:
        :return:
        """
        out_defect_task = defect_task.copy()

        # get suitable BULK calc by matching structures (right lattice
        # constant + same supercell size...) and matching essential INCAR + POTCAR settings...
        bulk_tasks = additional_tasks['bulksc']
        bulk_sm = StructureMatcher( ltol=self.ltol, stol=self.stol, angle_tol=self.angle_tol,
            primitive_cell=False, scale=False, attempt_supercell=False, allow_subset=False)
        bulk_matched = []
        dstruct_withoutdefect = Structure.from_dict(out_defect_task['transformations']['history'][0]['defect']['structure'])
        scaling_matrix = out_defect_task['transformations']['history'][0]['scaling_matrix']
        dstruct_withoutdefect.make_supercell( scaling_matrix)
        dincar = out_defect_task["calcs_reversed"][0]["input"]["incar"] #identify essential INCAR properties which differentiate different calcs
        dincar_reduced = {k: dincar.get(k, None) if dincar.get(k) not in  ['None', 'False', False] else None
                          for k in ["LHFCALC", "HFSCREEN", "IVDW", "LUSE_VDW", "LDAU", "METAGGA"]
                          }
        d_potcar_base = {'pot_spec': [potelt["titel"] for potelt in out_defect_task['input']['potcar_spec']],
                         'pot_labels': out_defect_task['input']['pseudo_potential']['labels'][:],
                         'pot_type': out_defect_task['input']['pseudo_potential']['pot_type'],
                         'functional': out_defect_task['input']['pseudo_potential']['functional']}

        for b_task in bulk_tasks:
            bstruct = Structure.from_dict(b_task['input']['structure'])
            if bulk_sm.fit( bstruct, dstruct_withoutdefect):
                #also match essential INCAR and POTCAR settings
                bincar = b_task["calcs_reversed"][0]["input"]["incar"]
                bincar_reduced = {k: bincar.get(k, None) if bincar.get(k) not in ['None', 'False', False] else None
                                  for k in dincar_reduced.keys()
                                  }

                b_potcar = {'pot_spec': set([potelt["titel"] for potelt in b_task['input']['potcar_spec']]),
                            'pot_labels': set(b_task['input']['pseudo_potential']['labels'][:]),
                            'pot_type': b_task['input']['pseudo_potential']['pot_type'],
                            'functional': b_task['input']['pseudo_potential']['functional']}
                d_potcar = d_potcar_base.copy() #need to reduce in cases of extrinsic species or reordering
                d_potcar['pot_spec'] = set([d for d in d_potcar['pot_spec'] if d in b_potcar['pot_spec']])
                d_potcar['pot_labels'] = set([d for d in d_potcar['pot_labels'] if d in b_potcar['pot_labels']])

                #track to make sure that cartesian coords are same (important for several levels of analysis in defect builder)
                same_cart_positions = True
                for bsite_coords in bstruct.cart_coords:
                    if not len( dstruct_withoutdefect.get_sites_in_sphere(bsite_coords, .1)):
                        same_cart_positions = False

                if bincar_reduced == dincar_reduced and b_potcar == d_potcar and same_cart_positions:
                    bulk_matched.append( b_task.copy())
                else:
                    try:
                        self.logger.debug("Bulk structure match was found for {} with {}, "
                                          "but:".format( b_task['task_label'], out_defect_task['task_label']))
                    except:
                        self.logger.debug("BULK STRUCT MATCH was found, but task_label did not exist AND:")
                    if bincar_reduced != dincar_reduced:
                        out_inc = {k:[v, bincar_reduced[k]] for k,v in dincar_reduced.items() if v != bincar_reduced[k]}
                        self.logger.debug("\tIncars were different: {} ".format( out_inc))
                    if b_potcar != d_potcar:
                        out_pot = {k:[v, b_potcar[k]] for k,v in d_potcar.items() if v != b_potcar[k]}
                        self.logger.debug("\tPotcar specs were different: {} ".format( out_pot))
                    if not same_cart_positions:
                        self.logger.debug("\tBulk site coords were different")

        #if bulk_task found then take most recently updated bulk_task for defect
        if len( bulk_matched):
            bulk_matched = sorted( bulk_matched, key=lambda x: x["last_updated"], reverse=True)
            out_defect_task["bulk_task"] = bulk_matched[0].copy()
            self.logger.debug("Found {} possible bulk supercell structures. Taking most recent entry updated "
                  "on: {}".format(len(bulk_matched), bulk_matched[0]['last_updated']))
        else:
            self.logger.error("Bulk task doesnt exist for: {} ({})! Cant create defect "
                             "object...\nMetadata: {}\n{}".format( out_defect_task['task_label'],
                                                                   out_defect_task['task_id'],
                                                                   d_potcar, dincar_reduced))
            return None


        # get suitable dielectric calc by matching structures (only lattice
        # constant fitting needed - not supercell) and POTCAR settings...
        diel_task_list = additional_tasks['diel']
        diel_sm = StructureMatcher( ltol=self.ltol, stol=self.stol, angle_tol=self.angle_tol,
            primitive_cell=True, scale=False, attempt_supercell=True, allow_subset=False)
        diel_matched = []
        for diel_task in diel_task_list:
            diel_struct = Structure.from_dict( diel_task['input']['structure'])
            if diel_sm.fit( diel_struct, dstruct_withoutdefect):
                #also match essential POTCAR settings and confirm LVTOT = True and LVHAR = True

                diel_potcar = {'pot_spec': set([potelt["titel"] for potelt in diel_task['input']['potcar_spec']]),
                            'pot_labels': set(diel_task['input']['pseudo_potential']['labels'][:]),
                            'pot_type': diel_task['input']['pseudo_potential']['pot_type'],
                            'functional': diel_task['input']['pseudo_potential']['functional']}
                d_potcar = d_potcar_base.copy() #need to reduce in cases of extrinsic species or reordering
                d_potcar['pot_spec'] = set([d for d in d_potcar['pot_spec'] if d in diel_potcar['pot_spec']])
                d_potcar['pot_labels'] = set([d for d in d_potcar['pot_labels'] if d in diel_potcar['pot_labels']])

                if diel_potcar == d_potcar:
                    diel_matched.append( diel_task.copy())
                else:
                    try:
                        self.logger.debug("Dielectric structure match was found for {} with {}, "
                                          "but:".format( diel_task['task_label'], out_defect_task['task_label']))
                    except:
                        self.logger.debug("Dielectric STRUCT MATCH was found, but task_label did not exist AND:")
                    out_pot = {k:[v, diel_potcar[k]] for k,v in d_potcar.items() if v != diel_potcar[k]}
                    self.logger.debug("\tPotcar specs were different: {} ".format( out_pot))
            # else:
            #     self.logger.debug("{} ({}) had a structure which did not match {} for use "
            #                       "as a dielectric calculation".format( diel_task['task_label'],
            #                                                          diel_task['task_id'],
            #                                                          out_defect_task['task_label']))

        #if diel_tasks found then take most recently updated bulk_task for defect
        if len( diel_matched):
            diel_matched = sorted( diel_matched, key=lambda x: x["last_updated"], reverse=True)
            diel_dict = {'diel_taskdb_task_id': diel_matched[0]['task_id'],
                         'epsilon_static': diel_matched[0]['output']['epsilon_static'],
                         'epsilon_ionic': diel_matched[0]['output']['epsilon_ionic']}
            out_defect_task["diel_task_meta"] = diel_dict.copy()
            self.logger.debug("Found {} possible dieletric calcs. Taking most recent entry updated "
                  "on: {}".format(len(diel_matched), diel_matched[0]['last_updated']))
        else:
            try:
                self.logger.error("Dielectric task doesnt exist for: {} ({})! Cant create defect "
                                 "object...\nMetadata for defect: {}\n{}".format( out_defect_task['task_label'],
                                                                                  out_defect_task['task_id'],
                                                                                  d_potcar, dincar_reduced))
            except:
                self.logger.debug("DIEL TASK DNE.")

            return None

        # FINALLY consider grabbing extra hybrid BS information...
        # first confirm from the INCAR setting that this defect is NOT an HSE calculation itself...
        if dincar_reduced['LHFCALC'] in [None, False, 'False'] and len(additional_tasks['hsebs']):
            hse_bs_matched = []
            for hse_bs_task in additional_tasks['hsebs']:
                hse_bs_struct = Structure.from_dict(hse_bs_task['input']['structure'])
                if diel_sm.fit(hse_bs_struct, dstruct_withoutdefect): #can use same matching scheme as the dielectric structure matcher
                    hse_bs_matched.append( hse_bs_task.copy())
                else:
                    self.logger.debug("task id {} has a structure which did not match {} for use "
                                      "as an HSE BS calculation".format( hse_bs_task['task_id'],
                                                                         out_defect_task['task_label']))

            if len(hse_bs_matched): #match the lowest CBM  and highest VBM values, keeping track of their task_ids
                hybrid_cbm_data = min([[htask['output']['cbm'], htask['task_id']] for htask in hse_bs_matched])
                hybrid_vbm_data = max([[htask['output']['vbm'], htask['task_id']] for htask in hse_bs_matched])
                hybrid_meta = {'hybrid_cbm': hybrid_cbm_data[0], 'hybrid_CBM_task_id': hybrid_cbm_data[1],
                               'hybrid_vbm': hybrid_vbm_data[0], 'hybrid_VBM_task_id': hybrid_vbm_data[1]}
                out_defect_task["hybrid_bs_meta"] = hybrid_meta.copy()
                self.logger.debug("Found hybrid band structure properties for {}:\n\t{}".format( out_defect_task['task_label'],
                                                                                               hybrid_meta))
            else:
                self.logger.debug("Could NOT find hybrid band structure properties for {} despite "
                                  "there being {} eligible hse calculations".format( out_defect_task['task_label'],
                                                                                     len(additional_tasks['hsebs'])))

        return out_defect_task

    def get_run_metadata(self, item, parameters):
        bulk_task = item['bulk_task']

        # load INCAR, KPOINTS, POTCAR and task_id (for both bulk and defect)
        potcar_summary = {'pot_spec': list([potelt["titel"] for potelt in item['input']['potcar_spec']]),
                          'pot_labels': list(item['input']['pseudo_potential']['labels'][:]),
                          'pot_type': item['input']['pseudo_potential']['pot_type'],
                          'functional': item['input']['pseudo_potential'][
                              'functional']}  # note bulk has these potcar values also, other wise it would not get to process_items
        dincar = item["input"]["incar"].copy()
        dincar_reduced = {k: dincar.get(k, None) for k in ["LHFCALC", "HFSCREEN", "IVDW", "LUSE_VDW",
                                                           "LDAU", "METAGGA"]}  # same as bulk
        bincar = item["input"]["incar"].copy()
        d_kpoints = item['calcs_reversed'][0]['input']['kpoints']
        if type(d_kpoints) != dict:
            d_kpoints = d_kpoints.as_dict()
        b_kpoints = bulk_task['calcs_reversed'][0]['input']['kpoints']
        if type(b_kpoints) != dict:
            b_kpoints = b_kpoints.as_dict()

        dir_name = item['calcs_reversed'][0]['dir_name']
        bulk_dir_name = bulk_task['calcs_reversed'][0]['dir_name']

        parameters['task_level_metadata'].update({'defect_dir_name': dir_name,
                                                  'bulk_dir_name': bulk_dir_name,
                                                  'bulk_taskdb_task_id': bulk_task['task_id'],
                                                  'potcar_summary': potcar_summary.copy(),
                                                  'incar_calctype_summary': dincar_reduced.copy(),
                                                  'defect_incar': dincar.copy(),
                                                  'bulk_incar': bincar.copy(),
                                                  'defect_kpoints': d_kpoints.copy(),
                                                  'bulk_kpoints': b_kpoints.copy(),
                                                  'defect_task_last_updated': item['last_updated']})

        if (dincar_reduced['HFSCREEN'] in [None, False, 'False']) and ("hybrid_bs_meta" in item):
            parameters.update({k: item["hybrid_bs_meta"][k] for k in ['hybrid_cbm', 'hybrid_vbm']})
            parameters.update({'hybrid_gap': parameters['hybrid_cbm'] - parameters['hybrid_vbm']})
            parameters['task_level_metadata'].update({k: item["hybrid_bs_meta"][k] for k in ['hybrid_CBM_task_id',
                                                                                             'hybrid_VBM_task_id']})
        return parameters

    def get_bulk_chg_correction_metadata(self, bulk_task, parameters):
        if 'locpot' in bulk_task['calcs_reversed'][0]['output'].keys():
            bulklpt = bulk_task['calcs_reversed'][0]['output']['locpot']
            axes = list(bulklpt.keys())
            axes.sort()
            parameters.update( {'bulk_planar_averages': [bulklpt[ax] for ax in axes]} )
        else:
            self.logger.error('BULKTYPEcalc: {} (task-id {}) does not '
                              'have locpot values for parsing'.format( bulk_task['task_label'],
                                                                       bulk_task['task_id']))

        if 'outcar' in bulk_task['calcs_reversed'][0]['output'].keys():
            bulkoutcar = bulk_task['calcs_reversed'][0]['output']['outcar']
            bulk_atomic_site_averages = bulkoutcar['electrostatic_potential']
            parameters.update( {'bulk_atomic_site_averages': bulk_atomic_site_averages})
        else:
            self.logger.error('BULKTYPEcalc: {} (task-id {}) does not '
                              'have outcar values for parsing'.format( bulk_task['task_label'],
                                                                       bulk_task['task_id']))
        return parameters

    def get_bulk_gap_data(self, bulk_task, parameters):
        bulk_structure = parameters['bulk_sc_structure']
        try:
            with MPRester() as mp:
                # mplist = mp.find_structure(bulk_structure) #had to hack this because this wasnt working??
                tmp_mplist = mp.get_entries_in_chemsys(list(bulk_structure.symbol_set))
            mplist = [ment.entry_id for ment in tmp_mplist if ment.composition.reduced_composition == \
                      bulk_structure.composition.reduced_composition]
            #TODO: this is a hack because find_structure was data intensive. simplify the hack to do less queries...
        except:
            raise ValueError("Error with querying MPRester for {}".format( bulk_structure.composition.reduced_formula))

        mpid_fit_list = []
        for trial_mpid in mplist:
            with MPRester() as mp:
                mpstruct = mp.get_structure_by_material_id(trial_mpid)
            if StructureMatcher(ltol=self.ltol, stol=self.stol, angle_tol=self.angle_tol,
                                primitive_cell=True, scale=False, attempt_supercell=True,
                                allow_subset=False).fit(bulk_structure, mpstruct):
                mpid_fit_list.append( trial_mpid)

        if len(mpid_fit_list) == 1:
            mpid = mpid_fit_list[0]
            self.logger.debug("Single mp-id found for bulk structure:{}.".format( mpid))
        elif len(mpid_fit_list) > 1:
            num_mpid_list = [int(mp.split('-')[1]) for mp in mpid_fit_list]
            num_mpid_list.sort()
            mpid  = 'mp-'+str(num_mpid_list[0])
            self.logger.debug("Multiple mp-ids found for bulk structure:{}\nWill use lowest number mpid "
                  "for bulk band structure = {}.".format(str(mpid_fit_list), mpid))
        else:
            self.logger.debug("Could not find bulk structure in MP database after tying the "
                              "following list:\n{}".format( mplist))
            mpid = None

        if mpid and not parameters['task_level_metadata']['incar_calctype_summary']['LHFCALC']:
            #TODO: NEED to be smarter about use of +U etc in MP gga band structure calculations...
            with MPRester() as mp:
                bs = mp.get_bandstructure_by_material_id(mpid)

            parameters['task_level_metadata'].update( {'MP_gga_BScalc_data':
                                                           bs.get_band_gap().copy()} ) #contains gap kpt transition
            cbm = bs.get_cbm()['energy']
            vbm = bs.get_vbm()['energy']
            gap = bs.get_band_gap()['energy']
        else:
            parameters['task_level_metadata'].update( {'MP_gga_BScalc_data': None}) #to signal no MP BS is used
            cbm = bulk_task['output']['cbm']
            vbm = bulk_task['output']['vbm']
            gap = bulk_task['output']['bandgap']

        parameters.update( {'mpid': mpid,
                            "cbm": cbm, "vbm": vbm, "gap": gap} )

        return parameters

    def load_defect_and_structure_data(self, defect_task, parameters):
        """
        This loads defect object from task_dict AND
        loads initial and final structures (making sure their sites are indexed in an equivalent manner)

        if can't confirm that indices are equivalent, then initial_defect_structure = None

        :param defect_task:
        :param parameters:
        :return:
        """

        if type(defect_task['transformations']) != dict:
            defect_task['transformations'] = defect_task['transformations'].as_dict()

        defect = defect_task['transformations']['history'][0]['defect']
        needed_keys = ['@module', '@class', 'structure', 'defect_site', 'charge', 'site_name']
        defect = MontyDecoder().process_decoded({k: v for k, v in defect.items() if k in needed_keys})

        scaling_matrix = MontyDecoder().process_decoded(defect_task['transformations']['history'][0]['scaling_matrix'])

        final_defect_structure = defect_task['output']['structure']
        if type(final_defect_structure) != Structure:
            final_defect_structure = Structure.from_dict(final_defect_structure)

        # build initial_defect_structure from very first ionic relaxation step (ensures they are indexed the same]
        initial_defect_structure = Structure.from_dict(
            defect_task['calcs_reversed'][-1]['output']['ionic_steps'][0]['structure'])

        # confirm structure matching
        ids = defect.generate_defect_structure(scaling_matrix)
        ids_sm = StructureMatcher( ltol=self.ltol, stol=self.stol, angle_tol=self.angle_tol,
                                   primitive_cell=False, scale=False, attempt_supercell=False,
                                   allow_subset=False)
        if not ids_sm.fit( ids, initial_defect_structure):
            self.logger.error("Could not match initial-to-final structure. Will not load initial structure.")
            initial_defect_structure = None

        parameters.update({'final_defect_structure': final_defect_structure,
                           'initial_defect_structure': initial_defect_structure,
                           'scaling_matrix': scaling_matrix})

        return defect, parameters

    def load_defect_chg_correction_metadata(self, defect, defect_task, parameters):

        # --> Load information for Freysoldt related parsing
        if 'locpot' in defect_task['calcs_reversed'][0]['output'].keys():
            deflpt = defect_task['calcs_reversed'][0]['output']['locpot']
            axes = list(deflpt.keys())
            axes.sort()
            defect_planar_averages = [deflpt[ax] for ax in axes]
            abc = parameters['initial_defect_structure'].lattice.abc
            axis_grid = []
            for ax in range(3):
                num_pts = len(defect_planar_averages[ax])
                axis_grid.append([i / num_pts * abc[ax] for i in range(num_pts)])
            parameters.update({'axis_grid': axis_grid,
                               'defect_planar_averages': defect_planar_averages})
        else:
            self.logger.error('DEFECTTYPEcalc: {} (task-id {}) does not have locpot values for '
                              'parsing Freysoldt correction'.format(defect_task['task_label'], defect_task['task_id']))


        # --> Load information for Kumagai related parsing
        if 'outcar' in defect_task['calcs_reversed'][0]['output'].keys() and \
                parameters['initial_defect_structure']:

            defoutcar = defect_task['calcs_reversed'][0]['output']['outcar']
            defect_atomic_site_averages = defoutcar['electrostatic_potential']
            bulk_sc_structure = parameters['bulk_sc_structure']
            initial_defect_structure = parameters['initial_defect_structure']

            bulksites = [site.frac_coords for site in bulk_sc_structure]
            initsites = [site.frac_coords for site in initial_defect_structure]
            distmatrix = initial_defect_structure.lattice.get_all_distances(bulksites, initsites) #first index of this list is bulk index
            min_dist_with_index = [[min(distmatrix[bulk_index]), int(bulk_index),
                                    int(distmatrix[bulk_index].argmin())] for bulk_index in range(len(distmatrix))] # list of [min dist, bulk ind, defect ind]

            found_defect = False
            site_matching_indices = []
            poss_defect = []
            if isinstance(defect, (Vacancy, Interstitial)):
                for mindist, bulk_index, defect_index in min_dist_with_index:
                    if mindist < self.ltol:
                        site_matching_indices.append( [bulk_index, defect_index])
                    elif isinstance(defect, Vacancy):
                        poss_defect.append( [bulk_index, bulksites[ bulk_index][:]])

                if isinstance(defect, Interstitial):
                    poss_defect = [ [ind, fc[:]] for ind, fc in enumerate(initsites) \
                                    if ind not in np.array(site_matching_indices)[:,1]]

            elif isinstance(defect, Substitution):
                for mindist, bulk_index, defect_index in min_dist_with_index:
                    species_match = bulk_sc_structure[bulk_index].specie == \
                                    initial_defect_structure[defect_index].specie
                    if mindist < self.ltol and species_match:
                        site_matching_indices.append( [bulk_index, defect_index])

                    elif not species_match:
                        poss_defect.append( [defect_index, initsites[ defect_index][:]])


            if len(poss_defect) == 1:
                found_defect = True
                defect_index_sc_coords = poss_defect[0][0]
                defect_frac_sc_coords = poss_defect[0][1]
            else:
                self.logger.error("Found {} possible defect sites when matching bulk and "
                                  "defect structure".format(len(poss_defect)))


            if len(set(np.array(site_matching_indices)[:, 0])) != len(set(np.array(site_matching_indices)[:, 1])):
                self.logger.error("Error occured in site_matching routine. Double counting of site matching "
                                  "occured:{}\nAbandoning Kumagai parsing.".format(site_matching_indices))
                found_defect = False

            # assuming Wigner-Seitz radius for sampling radius
            wz = initial_defect_structure.lattice.get_wigner_seitz_cell()
            dist = []
            for facet in wz:
                midpt = np.mean(np.array(facet), axis=0)
                dist.append(np.linalg.norm(midpt))
            sampling_radius = min(dist)

            if found_defect:
                parameters.update({'defect_atomic_site_averages': defect_atomic_site_averages,
                                   'site_matching_indices': site_matching_indices,
                                   'sampling_radius': sampling_radius,
                                   'defect_frac_sc_coords': defect_frac_sc_coords,
                                   'defect_index_sc_coords': defect_index_sc_coords})
            else:
                self.logger.error("Error in mapping procedure for bulk to initial defect structure.")

        else:
            self.logger.error('DEFECTTYPEcalc: {} (task-id {}) does not have outcar values for '
                              'parsing Kumagai'.format(defect_task['task_label'], defect_task['task_id']))

        return parameters


class DefectThermoBuilder(Builder):
    def __init__(self,
                 defects,
                 defectthermo,
                 query=None,
                 ltol=0.2,
                 stol=0.3,
                 angle_tol=5,
                 update_all=False,
                 **kwargs):
        """
        Creates DefectEntry from vasp task docs

        Args:
            defects (Store): Store of defect entries
            defectthermo (Store): Store of DefectPhaseDiagram documents
            query (dict): dictionary to limit materials to be analyzed (note query is for defects Store)
            ltol (float): StructureMatcher tuning parameter for matching tasks to materials
            stol (float): StructureMatcher tuning parameter for matching tasks to materials
            angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
            update_all (bool): Whether to consider all task ids from defects store.
                Default is False (will not re-consider task-ids which have been considered previously.
        """

        self.defects = defects
        self.defectthermo = defectthermo
        self.query = query if query else {}
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.update_all = update_all
        super().__init__(sources=[defects], targets=[defectthermo], **kwargs)

    def get_items(self):
        self.logger.info("DefectThermo Builder Started")

        # Save timestamp for update operation
        self.time_stamp = datetime.utcnow()

        #get all new Defect Entries since last time DefectThermo was updated...
        q = dict(self.query)
        self.logger.debug('query is initially: {}'.format( q))
        if not self.update_all:
            # if not update_all then grab entry_ids of defects that have been analyzed already...
            prev_dpd = list(self.defectthermo.query(properties=['metadata.all_entry_ids_considered']))
            self.logger.debug('Found {} previous dpd objects'.format( len(prev_dpd)))

            if "entry_id" not in q.keys():
                q["entry_id"] = {"$nin": []}
            elif "$nin" not in q["entry_id"].keys():
                q["entry_id"]["$nin"] = []
            for dpd in prev_dpd:
                q["entry_id"]["$nin"].extend( list( dpd['metadata']['all_entry_ids_considered']))

            self.logger.debug('query after removing previously considered entry_ids is: {}'.format( q))

        # q.update(self.defects.lu_filter(self.defectthermo))  #TODO: does this work?? / is it needed?

        # restricted amount of defect info for PD, so not an overwhelming database query
        entry_keys_needed_for_thermo = ['defect', 'parameters.task_level_metadata', 'parameters.last_updated',
                                        'task_id', 'entry_id', '@module', '@class',
                                        'uncorrected_energy', 'corrections', 'parameters.dielectric',
                                        'parameters.cbm', 'parameters.vbm', 'parameters.gap',
                                        'parameters.hybrid_cbm', 'parameters.hybrid_vbm',
                                        'parameters.hybrid_gap', 'parameters.potalign',
                                        'parameters.freysoldt_meta',
                                        'parameters.kumagai_meta', 'parameters.is_compatible',
                                        'parameters.delocalization_meta', 'parameters.phasediagram_meta']
        defect_entries = list(self.defects.query(criteria=q,
                                                        properties=entry_keys_needed_for_thermo))
        thermo_entries = list(self.defectthermo.query(properties=['bulk_chemsys', 'bulk_prim_struct',
                                                                  'run_metadata', 'entry_id']))
        self.logger.info("Found {} new defect entries to consider".format( len(defect_entries)))

        #group defect entries based on bulk types and task level metadata info

        sm = StructureMatcher(ltol=self.ltol, stol=self.stol, angle_tol=self.angle_tol,
                              primitive_cell=True, scale=False, attempt_supercell=True,
                                allow_subset=False)
        grpd_entry_list = []
        for entry_dict in defect_entries:
            #get bulk chemsys and struct
            base_bulk_struct = Structure.from_dict(entry_dict['defect']['structure'])
            base_bulk_struct = base_bulk_struct.get_primitive_structure()
            bulk_chemsys = "-".join(sorted((base_bulk_struct.symbol_set)))

            #get run metadata info
            entry_dict_md = entry_dict['parameters']['task_level_metadata']
            run_metadata = entry_dict_md['incar_calctype_summary'].copy()
            if 'potcar_summary' in entry_dict_md:
                run_metadata.update( entry_dict_md['potcar_summary'].copy())
                #only want to filter based on bulk POTCAR
                pspec, plab = set(), set()
                for symbol, full_potcar_label in zip(run_metadata['pot_labels'],
                                                     run_metadata['pot_spec']):
                    red_sym = symbol.split('_')[0]
                    if red_sym in base_bulk_struct.symbol_set:
                        pspec.add( symbol)
                        plab.add( full_potcar_label)

                run_metadata['pot_spec'] = "-".join(sorted(set(pspec))) #had to switch to this approach for proper dict comparison later on
                run_metadata['pot_labels'] = "-".join(sorted(set(plab)))

            # see if defect_entry matches an grouped entry list item already in progress
            # does this by matching bulk structure and run metadata
            matched = False
            for grp_ind, grpd_entry in enumerate(grpd_entry_list):
                if grpd_entry[0] == bulk_chemsys and grpd_entry[1] == run_metadata:
                    if sm.fit( base_bulk_struct, grpd_entry[2]):
                        grpd_entry[3].append( entry_dict.copy())
                        matched = True
                        break
                    else:
                        continue
                else:
                    continue

            if not matched: #have not logged yet, see if previous thermo phase diagram was created for this system
                for t_ent in thermo_entries:
                    if t_ent['bulk_chemsys'] == bulk_chemsys and t_ent['run_metadata'] == run_metadata:
                        if sm.fit(base_bulk_struct, Structure.from_dict(t_ent['bulk_prim_struct'])):
                            if not self.update_all:
                                #if not wanting to update everything, then get previous entries from thermo database
                                old_entry_set = list(self.defectthermo.query( {'entry_id': t_ent['entry_id']},
                                                                               properties=['entries']))[0]['entries']
                                old_entries_list = [entry.as_dict() if type(entry) != dict else entry for entry in
                                                    old_entry_set]
                            else:
                                old_entries_list = []

                            old_entries_list.append( entry_dict.copy())
                            grpd_entry_list.append( [bulk_chemsys, run_metadata.copy(),  base_bulk_struct.copy(),
                                                     old_entries_list, t_ent['entry_id']])
                            matched = True
                            break
                        else:
                            continue
                    else:
                        continue

            if not matched:
                # create new thermo phase diagram for this system,
                # entry_id will be generated later on
                grpd_entry_list.append( [bulk_chemsys, run_metadata.copy(), base_bulk_struct.copy(),
                                         [entry_dict.copy()], 'None'])


        for new_defects_for_thermo_entry in grpd_entry_list:
            yield new_defects_for_thermo_entry


    def process_item(self, items):
        #group defect entries into groups of same defect type (charge included)
        distinct_entries_full = [] #for storing full defect_dict
        distinct_entries = {} #for storing defect object
        bulk_chemsys, run_metadata, bulk_prim_struct, entrylist, entry_id = items
        self.logger.debug("Processing bulk_chemsys {}".format(bulk_chemsys))

        needed_entry_keys = ['@module', '@class', 'defect', 'uncorrected_energy', 'corrections',
                             'parameters', 'entry_id', 'task_id']
        pdc = PointDefectComparator(check_charge=True, check_primitive_cell=True, check_lattice_scale=False)
        for entry_dict in entrylist:
            entry = DefectEntry.from_dict({k:v for k,v in entry_dict.items() if k in needed_entry_keys})
            matched = False
            for grpind, grpdefect in distinct_entries.items():
                if pdc.are_equal( entry.defect, grpdefect.defect):
                    matched = True
                    break

            if matched:
                distinct_entries_full[grpind].append( entry_dict.copy())
            else:
                distinct_entries_full.append( [entry_dict.copy()])
                nxt_ind = max( distinct_entries.keys()) + 1 if len(distinct_entries.keys()) else 0
                distinct_entries[nxt_ind] = entry.copy()

        #now sort through entries and pick one that has been updated last (but track all previous entry_ids)
        all_entry_ids_considered, entries = [], []
        for ident_entries in distinct_entries_full:
            all_entry_ids_considered.extend([ent['entry_id'] for ent in ident_entries])
            # sort based on which was done most recently
            lu_list = []
            for ent_ind, ent in enumerate(ident_entries):
                try:
                    lu = ent['parameters']['task_level_metadata']['defect_task_last_updated']
                except:
                    lu = ent['parameters']['last_updated']
                if isinstance( lu, dict): #deal with case when datetime objects were not properly loaded
                    lu = MontyDecoder().process_decoded( lu)
                lu_list.append( [lu, ent_ind])
            try:
                lu_list.sort(reverse=True)
            except:
                for_print_lu_list = [[lu, ident_entries[ent_ind]['entry_id']] for lu, ent_ind in lu_list]
                raise ValueError("Error with last_updated sorting of list:\n{}".format( for_print_lu_list))
            recent_entry_dict = ident_entries[ lu_list[0][1]]

            new_entry = DefectEntry.from_dict( {k:v for k,v in recent_entry_dict.items() if k in needed_entry_keys})
            entries.append( new_entry.copy())

        # get vbm and bandgap; also verify all vbms and bandgaps are the same
        vbm = entries[0].parameters['vbm']
        band_gap = entries[0].parameters['gap']
        for ent in entries:
            if vbm != ent.parameters['vbm']:
                self.logger.error("Logging vbm = {} (retrieved from {}, task-id {}) but {} "
                                  "(task-id {}) has vbm = {}. Be careful with this defectphasediagram "
                                  "if these are very different".format( vbm, entries[0].name, entries[0].entry_id,
                                                                        ent.name, ent.entry_id, ent.parameters['vbm']))
            if band_gap != ent.parameters['gap']:
                self.logger.error("Logging gap = {} (retrieved from {}, task-id {}) but {} "
                                  "(task-id {}) has gap = {}. Be careful with this defectphasediagram "
                                  "if these are very different".format( band_gap, entries[0].name, entries[0].entry_id,
                                                                        ent.name, ent.entry_id, ent.parameters['gap']))

        defect_phase_diagram = DefectPhaseDiagram( entries, vbm, band_gap, filter_compatible=False,
                                                   metadata={'all_entry_ids_considered': all_entry_ids_considered})
        defect_phase_diagram_as_dict = defect_phase_diagram.as_dict()
        defect_phase_diagram_as_dict.update( {'bulk_chemsys': bulk_chemsys, 'bulk_prim_struct': bulk_prim_struct.as_dict(),
                                'run_metadata': run_metadata, 'entry_id': entry_id, 'last_updated': datetime.utcnow()})

        return defect_phase_diagram_as_dict

    def update_targets(self, items):
        list_entry_ids = list(self.defectthermo.distinct('entry_id'))
        if len(list_entry_ids):
            next_entry_id = max(list_entry_ids) + 1
        else:
            next_entry_id = 1
        for item in items:
            if item['entry_id'] == 'None':
                item['entry_id'] = next_entry_id
                next_entry_id += 1

        self.logger.info("Updating {} DefectThermo documents".format(len(items)))

        self.defectthermo.update(items, update_lu=True, key='entry_id')

