import os
from pymatgen.core import Structure, Element
from maggma.builders import Builder
from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.analysis.phase_diagram import PhaseDiagram, PhaseDiagramError
from pymatgen.transformations.standard_transformations import \
    PrimitiveCellTransformation
from itertools import chain, combinations
from itertools import groupby
from pymatgen.entries.computed_entries import ComputedStructureEntry
from pymatgen.apps.battery.insertion_battery import InsertionElectrode


s_hash = lambda el: el.data['comp_delith']
redox_els = ['Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Nb', 'Mo',
             'Sn', 'Sb', 'W', 'Re', 'Bi']
mat_props = ['structure', 'thermo.energy', 'calc_settings', 'task_id']

class ElectrodesBuilder(Builder):
    def __init__(self, materials, electro, working_ion, query=None,
                 compatibility=MaterialsProjectCompatibility("Advanced"),
                 **kwargs):
        """
        Calculates physical parameters of battery materials the battery entries using
        groups of ComputedStructureEntry and the entry for the most stable version of the working_ion in the system
        Args:
            materials (Store): Store of materials documents that contains the structures
            batt (Store): Store of thermodynamic data such as formation
                energy and decomposition pathway
            query (dict): dictionary to limit materials to be analyzed
            compatibility (PymatgenCompatability): Compatability module
                to ensure energies are compatible
        """
        self.sm = StructureMatcher(comparator=ElementComparator(),
                                   primitive_cell=False)
        self.materials = materials
        self.electro = electro
        self.working_ion = working_ion
        self.query = query if query else {}
        self.compatibility = compatibility
        self.completed_tasks = set()
        super().__init__(sources=[materials], targets=[electro], **kwargs)

    def get_items(self):
        """
        Get all entries by first obtaining the distinct chemical systems then
        sorting them by their composition (sans the working ion)

        Returns:
            set(ComputedStructureEntry): a set of entries for this system
        """

        # We only need the working_ion_entry once
        working_ion_entries = self.materials.query(criteria={"chemsys": self.working_ion}, properties=mat_props)
        working_ion_entries = self._mat_doc2comp_entry(working_ion_entries, store_struct=False)

        if working_ion_entries:
            self.working_ion_entry = min(working_ion_entries, key=lambda e: e.energy_per_atom)


        self.logger.info("Grabbing the relavant chemical systems containing the current \
                working ion and a single redox element.")
        q = dict(self.query)
        q.update({'$and': [
            {"elements": {'$in': [self.working_ion]}},
            {"elements": {'$in': redox_els}}
        ]})
        chemsys_names = self.materials.distinct('chemsys', q)
        for chemsys in chemsys_names:
            self.logger.debug("Calculating the phase diagram for: ", chemsys)
            print("Calculating the phase diagram for: ", chemsys)
            # get the phase diagram from using the chemsys
            pd_q = {'chemsys':{"$in": list(chemsys_permutations(chemsys))}}
            pd_docs = list(self.materials.query(properties=mat_props, criteria=pd_q))
            pd_ents = self._mat_doc2comp_entry(pd_docs, store_struct=False)
            pd_ents = list(filter(None.__ne__, pd_ents))
            for item in self.get_hashed_entries_from_chemsys(chemsys):
                item.update({'pd_ents':pd_ents})
                yield item

    def get_hashed_entries_from_chemsys(self, chemsys):
        """
        Read the entries from the thermo database and group them based on the reduced composition
        of the framework material (without working ion).
        Args:
            chemsys(string): the chemical system string to be queried
        returns:
            (chemsys, [group]): entry contains a list of entries the materials together by composition
        """
        # return the entries grouped by composition
        # then we will sort them
        elements = set(chemsys.split("-"))
        chemsys_w_wo_ion = {"-".join(sorted(c))
                for c in [elements, elements-{self.working_ion}]}
        self.logger.info("chemsys list: {}".format(chemsys_w_wo_ion))
        q = {'chemsys' : {"$in" : list(chemsys_w_wo_ion)}}
        docs = self.materials.query(q, mat_props)
        entries = self._mat_doc2comp_entry(docs)
        self.logger.info("Found {} entries in the database".format(len(entries)))
        entries = list(filter(None.__ne__, entries))
        print("Found {} entries in the database".format(len(entries)))



        if len(entries) > 1:
            # ignore systems with only one entry
            # group entries together by their composition sans the working ion
            entries = sorted(entries, key=s_hash)
            for _, g in groupby(entries, key=s_hash):
                g = list(g)
                self.logger.debug("The group: {}".format([el.composition for el in g]))
                if len(g) > 1:
                    #print('read')
                    yield {'chemsys': chemsys, 'all_entries': g}

    def process_item(self, item):
        """
        Read the entries from the thermo database and group them based on the reduced composition
        of the framework material (without working ion).
        Args:
            chemsys(string): the chemical system string to be queried
        returns:
            (chemsys, [group]): entry contains a list of entries the materials together by composition
        """
        # sort the entries intro subgroups
        # then perform PD analysis
        all_entries = item['all_entries']
        pd_ents = item['pd_ents']
        phdi = PhaseDiagram(pd_ents)

        grouped_entries = list(self.get_sorted_subgroups(all_entries))
        docs = [] # results 
        
        for group in grouped_entries:
            for en in group:
                self.logger.info(en.composition)
                # skip this d_muO2 stuff if you do note have oxygen
                if Element('O') in en.composition.elements:
                    d_muO2 = [
                        {'reaction' : str(itr['reaction']),
                         'chempot' : itr['chempot'],
                         'evolution' : itr['evolution']
                        }
                        for itr in phdi.get_element_profile('O', en.composition)
                    ]
                else:
                    d_muO2 = None
                en.data['muO2'] = d_muO2
                en.data['decomposition_energy'] = phdi.get_e_above_hull(en)

            #print([str(itr.data['muO2'])+"\n" for itr in group])
            result = InsertionElectrode(group, self.working_ion_entry)
            d = result.as_dict_summary()
            d['stable_entries'] = [{'entry_id': entry.entry_id, 'muO2': entry.data['muO2'],
                                        'decomposition_energy': entry.data['decomposition_energy']}
                                   for entry in result.get_stable_entries()]

            id_num = int(result.get_all_entries()[0].entry_id.split('-')[-1])
            d['batt_id'] = 'bat-' + str(id_num + 40000000)
            docs.append(d)
        return docs

    def update_targets(self, items):
        items = list(filter(None, chain.from_iterable(items)))
        if len(items) > 0:
            self.logger.info("Updating {} thermo documents".format(len(items)))
            self.electro.update(docs=items, key='batt_id')
        else:
            self.logger.info("No items to update")
    
    def get_sorted_subgroups(self, group):
        matching_subgroups = list(self.group_entries(group))
        if matching_subgroups:
            for subg in matching_subgroups:
                wion_conc = set()
                for el in subg:
                    wion_conc.add(el.composition.fractional_composition[self.working_ion])
                if len(wion_conc) > 1:
                    yield subg
                else:
                    del subg

    def group_entries(self, g):
        """
        group the structures together based on similarity of the delithiated primitive cells

        Args:
            g: a list of entries
        Returns:
            subgroups: subgroups that are grouped together based on structure
        """

        def match_in_group(ref, sub_list):
            for el in sub_list:
                if self.sm.fit(ref.data['structure_delith'], el[1].data['structure_delith']):
                    return True
            return False

        unmatched = list(enumerate(g))
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

    def _chemsys_delith(self, chemsys):
        # get the chemsys with the working ion removed from the set
        elements = set(chemsys.split("-"))
        return {"-".join(sorted(c))
                for c in [elements, elements-{self.working_ion}]}

    def _mat_doc2comp_entry(self, docs, store_struct=True):
        def get_prim_host(struct):
            """
            Get the primitive structure with all of the lithiums removed
            """
            structure = struct.copy()
            structure.remove_species([self.working_ion])
            prim = PrimitiveCellTransformation()
            return prim.apply_transformation(structure)
        
        entries=[]
        for d in docs:
            struct = Structure.from_dict(d['structure'])
            en = ComputedStructureEntry(structure=struct,
                                        energy=d['thermo']['energy'],
                                        parameters=d['calc_settings'],
                                        entry_id=d['task_id'],
                                        )
            if store_struct:
                struct_delith = get_prim_host(struct)
                comp_delith = self.sm._comparator.get_hash(struct_delith.composition)
                #new_entry.data['structure'] = struct
                en.data['structure_delith'] = struct_delith
                en.data['comp_delith'] = comp_delith
            entries.append(self.compatibility.process_entry(en))
        return entries

def chemsys_permutations(chemsys):
    # Fancy way of getting every unique permutation of elements for all
    # possible number of elements:
    elements = chemsys.split("-")
    return {"-".join(sorted(c))
            for c in chain(*[combinations(elements, i)
                            for i in range(1, len(elements) + 1)])}
