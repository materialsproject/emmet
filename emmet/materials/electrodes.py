import os
from pymatgen.core import Structure, Composition
from maggma.stores import MongoStore
from maggma.builder import Builder
from emmet.common.utils import load_settings
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.analysis.phase_diagram import PhaseDiagram, PhaseDiagramError
from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.transformations.standard_transformations import \
PrimitiveCellTransformation
from itertools import chain, combinations
from itertools import groupby
from pymatgen import MPRester
from pymatgen.entries.computed_entries import ComputedStructureEntry
from pymatgen.analysis.phase_diagram import PhaseDiagram
from db_battery import DbInsertionElectrode


default_substrate_settings = os.path.join("/Users/lik/repos/emmet/emmet/materials/settings", "electrodes.yaml") # TODO this substrate file needs to be updated

class ElectrodesBuilder(Builder):
    s_hash = lambda el : el.data['comp_delith']
    redox_els = ['Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Nb', 'Mo',
'Sn', 'Sb', 'W', 'Re', 'Bi']

    def __init__(self, materials, thermo, electro, working_ion, query=None,
                 compatibility=MaterialsProjectCompatibility("Advanced"),
                 **kwargs):
        """
        Calculates physical parameters of battery materials 
        Args:
            materials (Store): Store of materials documents
            batt (Store): Store of thermodynamic data such as formation
                energy and decomposition pathway
            query (dict): dictionary to limit materials to be analyzed
            compatibility (PymatgenCompatability): Compatability module
                to ensure energies are compatible
        """
        self.sm = StructureMatcher(comparator=ElementComparator(), primitive_cell=False)
        self.materials = materials
        self.thermo = thermo
        self.electro = electro
        self.working_ion = working_ion
        self.query = query if query else {}
        self.compatibility = compatibility
        self.completed_tasks = set()

        super().__init__(sources=[materials], targets=[electro], **kwargs)

    def get_items(self):
        # hash to group the structures by
        #s_hash = lambda el : self.sm._comparator.get_hash(el.data['comp_delith'])
        self.logger.info("Grabbing the relavant chemical systems containing the current \
                working ion and a single redox element.")
        q = dict(self.query)
        q.update({'$and' : [
            {"elements": {'$in' : [self.working_ion]}},
            {"elements": {'$in' : ElectrodesBuilder.redox_els}}
        ]})
        chemsys_names = self.materials.distinct('chemsys', q)
        for chemsys in chemsys_names:
            return (self.get_hashed_entries_from_chemsys(chemsys))

    
    def get_hashed_entries_from_chemsys(self, chemsys):
        # return the entries grouped by composition
        # then we will sort them 
        elements = set(chemsys.split("-"))
        chemsys_w_wo_ion = {"-".join(sorted(c))
                for c in [elements, elements-{self.working_ion}]}
        # print("chemsys list: {}".format(chemsys_w_wo_ion))
        q = {'chemsys' : {"$in" : list(chemsys_w_wo_ion)}}
        #p = ['structure', 'final_energy_per_atom','unit_cell_formula', 'pretty_formula', 'elements','task_id']
        th_docs = self.thermo.collection.find(q)
        entries = self.thermo_doc2comp_entry(th_docs)
        
        self.logger.debug("Fround {} entries in the database".format(len(entries)))
        if len(entries) > 1:
            # ignore systems with only one entry
            # group entries together by their composition sans the working ion
            del th_docs
            entries = sorted(entries, key = ElectrodesBuilder.s_hash)
            for k, g in groupby(entries, key=ElectrodesBuilder.s_hash):
                g = list(g)
                self.logger.debug("The group: {}".format([el.composition for el in g]))
                if len(g) > 1:
                    yield (chemsys, g)
    
    def test_p(self, item_list):
        for item in item_list:
            self.process_item(item)
                    
    def process_item(self, item):
        working_ion_entries = self.thermo.collection.find({"chemsys": self.working_ion})
        working_ion_entries = self.thermo_doc2comp_entry(working_ion_entries, store_struct=False)
        if working_ion_entries:
            working_ion_entry = min(working_ion_entries, key=lambda e: e.energy_per_atom)
            
        # sort the entries intro subgroups
        # then perform PD analysis
        chemsys = item[0]
        all_entries = item[1]
        phdi = self.get_pd_from_chemsys(chemsys)
        # obtain the pd
        grouped_entries = self.get_sorted_subgroups(all_entries)
        for group in grouped_entries:
            print('processing group:', [el.entry_id for el in group])
            results = DbInsertionElectrode(group, working_ion_entry)
            try:
                # in some cases entries in a group might be too far above the covex hull which will break
                # InsertionElectrode, in those case we can just ignore those entries
                #results = DBInsertionElectrode(group, working_ion_entry)
                yield results
            except:
                print('FAILED')

    def get_pd_from_chemsys(self, chemsys):
        elements = chemsys.split("-")
        chemsys_pd = {"-".join(sorted(c))
                for c in chain(*[combinations(elements, i)
                    for i in range(1, len(elements) + 1)])}
        q = {'chemsys' : {"$in" : list(chemsys_pd)}}
        th_docs = self.thermo.collection.find(q)
        pd_entries = self.thermo_doc2comp_entry(th_docs, store_struct=False)
        phdi = PhaseDiagram(pd_entries)
        return phdi
    
    def get_sorted_subgroups(self, group):
        #self.logger.debug("This group is being parsed for similarities to the collection: {}".format([el.entry_id for el in g]))
        matching_subgroups = list(self.group_entries(group))
        if matching_subgroups:
            for subg in matching_subgroups:
                wion_conc = set()
                for el in subg:
                    # get the working_ion concentration in each structure
                    wion_conc.add(el.composition.fractional_composition[self.working_ion])
                if len(wion_conc) > 1:
                    yield subg
                else:
                    del subg

    def group_entries(self, group):
        """
        group the structures together based on similarity of the delithiated primitive cells

        Args:
            g: a list of entries with fields ['structure', 'chemsys','reduced_cell_formula', 'task_id']
        Returns:
            subgroups: subgroups that are grouped together based on structure
        """

        def match_in_group(ref, sub_list):
            for el in sub_list:
                if self.sm.fit(ref.data['structure_delith'], el[1].data['structure_delith']):
                    return True
            return False

        unmatched = list(enumerate(group))
        subgroups = None
        while len(unmatched) > 0:
            i, refs = unmatched.pop(0)
            if subgroups == None:
                subgroups=[[(i, refs)]]
                continue
            g_inds = filter(lambda itr: match_in_group(refs, subgroups[itr]),
                              list(range(len(subgroups))))
            g_inds = list(g_inds)  # list of all matching subgroups
            if not g_inds:
                subgroups.append([(i, refs)])
            else:
                if len(g_inds) > 1:
                    new_group = list(chain.from_iterable(subgroups[i] for i in g_inds))
                    for idx in sorted(g_inds, reverse=True):
                        del subgroups[idx]
                    subgroups.append(new_group)
                    # add to the end
                    g_inds = [len(subgroups)]
                else:
                    subgroups[g_inds[0]].append((i, refs))

        for sg in subgroups:
            if len(sg)>1:
                #print([(el[1]['task_id'], el[1]['pretty_formula']) for el in sg])
                yield [el[1] for el in sg]

    def chemsys_delith(self, chemsys):
        # Fancy way of getting every unique permutation of elements for all
        # possible number of elements:
        elements = set(chemsys.split("-"))
        return {"-".join(sorted(c))
                for c in [elements, elements-{self.working_ion}]}

    def thermo_doc2comp_entry(self, th_docs, store_struct = True):
        def get_prim_host(struct):
            """
            Get the primitive structure with all of the lithiums removed
            """
            structure = struct.copy()
            structure.remove_species(['Li'])
            prim = PrimitiveCellTransformation()
            return prim.apply_transformation(structure)
        
        entries=[]
        for th_doc in th_docs:
            q = {'task_ids' : {'$in' : [th_doc['task_id']]}}
            p = ['structure', 'task_id']
            mdoc = self.materials.collection.find_one(q, projection=p)
            struct = Structure.from_dict(mdoc['structure'])
            th_doc['thermo']['entry']['structure'] = struct
            new_entry = ComputedStructureEntry.from_dict(th_doc['thermo']['entry'])
            if store_struct:
                struct_delith = get_prim_host(struct)             
                comp_delith = self.sm._comparator.get_hash(struct_delith.composition)
                #new_entry.data['structure'] = struct
                new_entry.data['structure_delith'] = struct_delith
                new_entry.data['comp_delith'] = comp_delith
            entries.append(self.compatibility.process_entry(new_entry))
        return entries
            
        
    
    def mp_doc2comp_entry(self, mp_docs, store_struct = True):
        def get_prim_host(struct):
            """
            Get the primitive structure with all of the lithiums removed
            """
            structure = struct.copy()
            structure.remove_species(['Li'])
            prim = PrimitiveCellTransformation()
            return prim.apply_transformation(structure)
        
        entries=[]
        for mdoc in mp_docs:
            if store_struct:
                struct = Structure.from_dict(mdoc['structure'])
                struct_delith = get_prim_host(struct)             
                comp_delith = self.sm._comparator.get_hash(struct_delith.composition)

            # Compatibility
            func = mdoc["pseudo_potential"]["functional"]
            labels = mdoc["pseudo_potential"]["labels"]
            symbols = ["{} {}".format(func, label) for label in labels]
            parameters = {"run_type": mdoc["run_type"],
                "is_hubbard": mdoc["is_hubbard"],
                "hubbards": mdoc["hubbards"],
                "potcar_symbols": symbols}

            if store_struct:
                new_entry = ComputedStructureEntry(
                        structure = struct,
                        composition = Composition(mdoc['unit_cell_formula']),
                        energy = mdoc['final_energy'],
                        parameters = parameters,
                        entry_id = mdoc['task_id'],
                        data = {'structure' : struct, 'structure_delith' : struct_delith, 
                                'pretty_formula' : mdoc['pretty_formula'], 'elements' : mdoc['elements'],
                                'comp_delith' : comp_delith}
                )
            else:
                new_entry = ComputedStructureEntry(
                        structure = struct,
                        composition = Composition(mdoc['unit_cell_formula']),
                        energy = mdoc['final_energy'],
                        parameters = parameters,
                        entry_id = mdoc['task_id']
                )
                
            
            entries.append(self.compatibility.process_entry(new_entry))
        return entries
        
    def update_targets(self):
        pass

    