from pymatgen.core import Structure, Element
from maggma.builders import Builder
from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from pymatgen.analysis.structure_matcher import (
    StructureMatcher, ElementComparator
)

from pymatgen.analysis.phase_diagram import PhaseDiagram, PhaseDiagramError
from pymatgen.transformations.standard_transformations import \
    PrimitiveCellTransformation
from itertools import chain, combinations
from itertools import groupby
from pymatgen.entries.computed_entries import ComputedStructureEntry, ComputedEntry
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.apps.battery.conversion_battery import ConversionElectrode
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen import Composition
from emmet.materials.thermo import chemsys_permutations
from pymatgen.analysis.structure_analyzer import oxide_type
from numpy import unique
import operator

__author__ = "Jimmy Shen"
__email__ = "jmmshn@lbl.gov"

def s_hash(el):
    return el.data['comp_delith']


redox_els = [
    'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Nb', 'Mo', 'Sn', 'Sb', 'W',
    'Re', 'Bi', 'C', 'Hf'
]
mat_props = [
    'structure',
    'calc_settings',
    'task_id',
    '_sbxn',
    'entries',
    'formula_pretty']

sg_fields = ["number", "hall_number", "international", "hall", "choice"]


def generic_groupby(list_in, comp=operator.eq):
    """
    Group a list of unsortable objects
    Args:
        list_in: A list of generic objects
        comp: (Default value = operator.eq) The comparator
    Returns:
        [int] list of labels for the input list
    """
    list_out = [None] * len(list_in)
    label_num = 0
    for i1, ls1 in enumerate(list_out):
        if ls1 is not None:
            continue
        list_out[i1] = label_num
        for i2, ls2 in list(enumerate(list_out))[i1 + 1:]:
            if comp(list_in[i1], list_in[i2]):
                if list_out[i2] is None:
                    list_out[i2] = list_out[i1]
                else:
                    list_out[i1] = list_out[i2]
                    label_num -= 1
        label_num += 1
    return list_out


class ElectrodesBuilder(Builder):
    def __init__(self,
                 materials,
                 electro,
                 working_ion,
                 query=None,
                 compatibility=None,
                 **kwargs):
        """
        Calculates physical parameters of battery materials the battery entries using
        groups of ComputedStructureEntry and the entry for the most stable version of the working_ion in the system
        Args:
            materials (Store): Store of materials documents that contains the structures
            electro (Store): Store of insertion electrodes data such as voltage and capacity
            query (dict): dictionary to limit materials to be analyzed ---
                            only applied to the materials when we need to group structures
                            the phase diagram is still constructed with the entire set
            compatibility (PymatgenCompatability): Compatability module
                to ensure energies are compatible
        """
        self.materials = materials
        self.electro = electro
        self.working_ion = working_ion
        self.query = query if query else {}
        self.compatibility = (
            compatibility
            if compatibility
            else MaterialsProjectCompatibility("Advanced")
        )
        self.completed_tasks = set()

        self.sm = StructureMatcher(
            comparator=ElementComparator(),
            primitive_cell=True,
            ignored_species=[
                self.working_ion])
        super().__init__(sources=[materials], targets=[electro], **kwargs)

    def get_items(self):
        """
        Get all entries by first obtaining the distinct chemical systems then
        sorting them by their composition (sans the working ion)

        Returns:
            list of dictionaries with keys 'chemsys' 'elec_entries' and 'pd_entries'
            the entries in 'elec_entries' contain all of the structures for insertion electrode analysis
            the entries in 'pd_entries' contain the information to generate the phase diagram
        """

        # We only need the working_ion_entry once
        # working_ion_entries = self.materials.query(criteria={"chemsys": self.working_ion}, properties=mat_props)
        # working_ion_entries = self._mat_doc2comp_entry(working_ion_entries, store_struct=False)
        #
        # if working_ion_entries:
        #     self.working_ion_entry = min(working_ion_entries, key=lambda e: e.energy_per_atom)

        self.logger.info(
            "Grabbing the relavant chemical systems containing the current working ion and a single redox element.")
        q = dict()
        q.update({
            '$and': [{
                "elements": {
                    '$in': [self.working_ion]
                }
            }, {
                "elements": {
                    '$in': redox_els
                }
            }]
        })
        q.update(self.query)

        chemsys_names = self.materials.distinct('chemsys', q)
        self.logger.debug(f'chemsys_names: {chemsys_names}')
        for chemsys in chemsys_names:
            self.logger.debug(f"Calculating the phase diagram for: {chemsys}")
            # get the phase diagram from using the chemsys
            pd_q = {
                'chemsys': {
                    "$in": list(chemsys_permutations(chemsys))
                },
                'deprecated': False
            }
            self.logger.debug(f"pd_q: {pd_q}")
            pd_docs = list(
                self.materials.query(properties=mat_props, criteria=pd_q))
            pd_ents = self._mat_doc2comp_entry(
                pd_docs, is_structure_entry=True)
            pd_ents = list(filter(None.__ne__, pd_ents))

            for item in self.get_hashed_entries_from_chemsys(chemsys):
                item.update({'pd_entries': pd_ents})

                ids_all_ents = {ient.entry_id for ient in item['elec_entries']}
                ids_pd = {ient.entry_id for ient in item['pd_entries']}
                assert(ids_all_ents.issubset(ids_pd))
                self.logger.debug(
                    f"all_ents [{[ient.composition.reduced_formula for ient in item['elec_entries']]}]"
                )
                self.logger.debug(
                    f"pd_entries [{[ient.composition.reduced_formula for ient in item['pd_entries']]}]"
                )
                yield item

    def get_hashed_entries_from_chemsys(self, chemsys):
        """
        Read the entries from the materials database and group them based on the reduced composition
        of the framework material (without working ion).
        Args:
            chemsys(string): the chemical system string to be queried
        returns:
            (chemsys, [group]): entry contains a list of entries the materials together by composition
        """
        # return the entries grouped by composition
        # then we will sort them
        elements = set(chemsys.split("-"))
        chemsys_w_wo_ion = {
            "-".join(sorted(c))
            for c in [elements, elements - {self.working_ion}]
        }
        self.logger.info("chemsys list: {}".format(chemsys_w_wo_ion))
        q = {"$and": [{'chemsys': {"$in": list(chemsys_w_wo_ion)}, 'formula_pretty': {
            '$ne': self.working_ion}, 'deprecated': False}, self.query]}
        self.logger.debug(f"q: {q}")
        docs = self.materials.query(q, mat_props)
        entries = self._mat_doc2comp_entry(docs)
        entries = list(filter(lambda x: x is not None, entries))
        self.logger.debug(
            f"entries found using q [{[ient.composition.reduced_formula for ient in entries]}]"
        )
        self.logger.info("Found {} entries in the database".format(
            len(entries)))
        entries = list(filter(None.__ne__, entries))

        if len(entries) > 1:
            # ignore systems with only one entry
            # group entries together by their composition sans the working ion
            entries = sorted(entries, key=s_hash)
            for _, g in groupby(entries, key=s_hash):
                g = list(g)
                self.logger.debug(
                    "The full group of entries found based on chemical formula alone: {}"
                    .format([el.name for el in g]))
                if len(g) > 1:
                    yield {'chemsys': chemsys, 'elec_entries': g}

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
        elec_entries = item['elec_entries']
        pd_ents = item['pd_entries']
        phdi = PhaseDiagram(pd_ents)

        # The working ion entries
        ents_wion = list(
            filter(
                lambda x: x.composition.get_integer_formula_and_factor()[0] == self.working_ion, pd_ents))
        working_ion_entry = min(ents_wion,
                                key=lambda e: e.energy_per_atom)
        assert (working_ion_entry is not None)

        grouped_entries = list(self.get_sorted_subgroups(elec_entries))
        docs = []  # results

        for group in grouped_entries:
            self.logger.debug(
                f"Grouped entries in all sandboxes {', '.join([en.name for en in group])}"
            )
            for en in group:
                # skip this d_muO2 stuff if you do note have oxygen
                if Element('O') in en.composition.elements:
                    d_muO2 = [{
                        'reaction': str(itr['reaction']),
                        'chempot': itr['chempot'],
                        'evolution': itr['evolution']
                    } for itr in phdi.get_element_profile('O', en.composition)]
                else:
                    d_muO2 = None
                en.data['muO2'] = d_muO2
                en.data['decomposition_energy'] = phdi.get_e_above_hull(en)

            # sort out the sandboxes
            # for each sandbox core+sandbox will both contribute entries
            all_sbx = [ent.data['_sbxn'] for ent in group]
            all_sbx = set(chain.from_iterable(all_sbx))
            self.logger.debug(f"All sandboxes {', '.join(list(all_sbx))}")

            for isbx in all_sbx:
                group_sbx = list(
                    filter(
                        lambda ent: (isbx in ent.data['_sbxn']) or (ent.data[
                            '_sbxn'] == ['core']), group))
                # Need more than one level of lithiation to define a electrode
                # material
                if len(group_sbx) == 1:
                    continue
                self.logger.debug(
                    f"Grouped entries in sandbox {isbx} -- {', '.join([en.name for en in group_sbx])}"
                )

                try:
                    result = InsertionElectrode(group_sbx,
                                                working_ion_entry)
                    assert (len(result._stable_entries) > 1)
                except AssertionError:
                    # The stable entries did not form a hull with the Li entry
                    self.logger.warn(
                        f"Not able to generate a  entries in sandbox {isbx} using the following entires-- \
                            {', '.join([str(en.entry_id) for en in group_sbx])}"
                    )
                    continue

                spacegroup = SpacegroupAnalyzer(
                    result.get_stable_entries(
                        charge_to_discharge=True)[0].structure)
                d = result.as_dict_summary()
                ids = [entry.entry_id for entry in result.get_all_entries()]
                lowest_id = sorted(ids, key=lambda x: x.split('-')[-1])[0]
                d['spacegroup'] = {
                    k: spacegroup._space_group_data[k]
                    for k in sg_fields
                }

                if isbx == 'core':
                    d['battid'] = lowest_id + '_' + self.working_ion
                else:
                    d['battid'] = lowest_id + '_' + \
                        self.working_ion + '_' + isbx
                # Only allow one sandbox value for each electrode
                d['_sbxn'] = [isbx]

                # store the conversion profile up to the discharged compositions
                f, v = self.get_competing_conversion_electrode_profile(Composition(d['formula_discharge']), phase_diagram=phdi)
                d['conversion_data'] = {'fracA_charge_discharge': f,
                                        'conversion_voltage' : v}
                docs.append(d)

        return docs

    def update_targets(self, items):
        items = list(filter(None, chain.from_iterable(items)))
        if len(items) > 0:
            self.logger.info("Updating {} electro documents".format(
                len(items)))
            self.electro.update(docs=items, key=['battid'])
        else:
            self.logger.info("No items to update")

    def get_sorted_subgroups(self, group):
        matching_subgroups = list(self.group_entries(group))
        if matching_subgroups:
            for subg in matching_subgroups:
                wion_conc = set()
                for el in subg:
                    wion_conc.add(el.composition.fractional_composition[
                        self.working_ion])
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
        labs = generic_groupby(
            g,
            comp=lambda x, y: any(
                [
                    self.sm.fit(x.structure, y.structure),
                    self.sm.fit(y.structure, x.structure),
                ]
            ),
        )  # because fit is not commutitive
        for ilab in unique(labs):
            sub_g = [g[itr] for itr, jlab in enumerate(labs) if jlab == ilab]
            if len(sub_g) > 1:
                yield [el for el in sub_g]

    def _chemsys_delith(self, chemsys):
        # get the chemsys with the working ion removed from the set
        elements = set(chemsys.split("-"))
        return {
            "-".join(sorted(c))
            for c in [elements, elements - {self.working_ion}]
        }

    def _mat_doc2comp_entry(self, docs, is_structure_entry=True):
        def get_prim_host(struct):
            """
            Get the primitive structure with all of the lithiums removed
            """
            structure = struct.copy()
            structure.remove_species([self.working_ion])
            prim = PrimitiveCellTransformation()
            return prim.apply_transformation(structure)

        entries = []

        for d in docs:
            struct = Structure.from_dict(d['structure'])
            # get the calc settings
            entry_type = "gga_u" if "gga_u" in d["entries"] else "gga"
            d["entries"][entry_type]["correction"] = 0.0
            if is_structure_entry:
                d["entries"][entry_type]["structure"] = struct
                en = ComputedStructureEntry.from_dict(d["entries"][entry_type])
            else:
                en = ComputedEntry.from_dict(d["entries"][entry_type])

            en.data["_sbxn"] = d.get("_sbxn", [])

            if en.composition.reduced_formula != self.working_ion:
                dd = en.composition.as_dict()
                if self.working_ion in dd:
                    dd.pop(self.working_ion)
                en.data['comp_delith'] = Composition.from_dict(
                    dd).reduced_formula

            en.data["oxide_type"] = oxide_type(struct)

            try:
                entries.append(self.compatibility.process_entry(en))
            except BaseException:
                self.logger.warn(
                    'unable to process material with task_id: {}'.format(
                        en.entry_id))
        return entries

    def get_competing_conversion_electrode_profile(self, comp, phase_diagram):
        """
        Take the composition and draw the conversion electrode profile
        Stop drawing the profile once the working ion content of the conversion electrode reaches the maximum content of the specificed composition


        Returns:

        """

        ce = ConversionElectrode.from_composition_and_pd(comp=comp,
                                                         pd=phase_diagram,
                                                         working_ion_symbol=self.working_ion,
                                                         allow_unstable=True,
                                                         )

        max_frac = comp.get_atomic_fraction(self.working_ion)
        frac_woin = []
        avg_voltage = []
        for itr in ce.get_summary_dict()['adj_pairs']:
            if itr['fracA_charge'] > max_frac:
                break
            frac_woin.append([itr['fracA_charge'], itr['fracA_discharge']])
            avg_voltage.append(itr['average_voltage'])

        return frac_woin, avg_voltage


