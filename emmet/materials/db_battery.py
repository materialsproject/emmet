"""
This module is used for analysis of materials with potential application as
batteries.
"""
from __future__ import division

__author__ = "Anubhav Jain, Shyue Ping Ong"
__copyright__ = "Copyright 2012, The Materials Project"
__version__ = "0.1"
__maintainer__ = "Anubhav Jain"
__email__ = "ajain@lbl.gov"
__date__ = "Jan 13, 2012"


from pymatgen import Element, Composition
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.apps.battery.conversion_battery import ConversionVoltagePair, \
    ConversionElectrode


class DbInsertionElectrode(InsertionElectrode):
    """
    A set of topotactically related compounds, with different amounts of a
    single element, e.g. TiO2 and LiTiO2,
    that can be used to define an insertion battery electrode.
    """

    def to_dict_summary(self, print_subelectrodes=True):
        """
        Arguments:
            print_subelectrodes:
                Also print data on all the possible subelectrodes
        
        Returns:
            a summary of this electrode"s properties in dictionary format
        """

        d = {}
        d["average_voltage"] = self.get_average_voltage()
        d["max_voltage"] = self.max_voltage
        d["min_voltage"] = self.min_voltage
        d["max_delta_volume"] = self.max_delta_volume
        d["max_voltage_step"] = self.max_voltage_step
        d["capacity_grav"] = self.get_capacity_grav()
        d["capacity_vol"] = self.get_capacity_vol()
        d["energy_grav"] = self.get_specific_energy()
        d["energy_vol"] = self.get_energy_density()
        d["working_ion"] = self._working_ion.symbol
        d["nsteps"] = self.num_steps
        d["material_ids"] = [e.entry_id for e in self.get_all_entries()]
        d["stable_material_ids"] = [e.entry_id for e in self.get_stable_entries()]
        d["unstable_material_ids"] = [e.entry_id for e in self.get_unstable_entries()]
        d["id_charge"] = self.fully_charged_entry.entry_id
        d["id_discharge"] = self.fully_discharged_entry.entry_id
        d["framework"] = composition_to_multi_dict(self._vpairs[0].framework)
        d["formula_charge"] = self.fully_charged_entry.composition.reduced_formula
        d["formula_discharge"] = self.fully_discharged_entry.composition.reduced_formula
        d["fracA_charge"] = self.fully_charged_entry.composition.get_atomic_fraction(self.working_ion)
        d["fracA_discharge"] = self.fully_discharged_entry.composition.get_atomic_fraction(self.working_ion)
        d["max_instability"] = self.get_max_instability()
        d["min_instability"] = self.get_min_instability()
        d["stability_data"] = dict([(e.entry_id, e.data["decomposition_energy"])
                                    for e in self.get_all_entries()
                                    if "decomposition_energy" in e.data])
        d['stability_charge'] = d['stability_data'][self.fully_charged_entry.entry_id]
        d['stability_discharge'] = d['stability_data'][self.fully_discharged_entry.entry_id]
        d["muO2_data"] = dict([(e.entry_id, e.data["muO2"])
                               for e in self.get_all_entries()
                               if "muO2" in e.data])
        if print_subelectrodes:
            f_dict = lambda c: c.to_dict_summary(print_subelectrodes=False)
            d["adj_pairs"] = map(f_dict, self.get_sub_electrodes(adjacent_only=True))
            d["all_pairs"] = map(f_dict, self.get_sub_electrodes(adjacent_only=False))
        return d

    @property
    def to_dict(self):
        return self.to_dict_summary()

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "DbInsertionElectrode with endpoints at %s and %s, average voltage %f, capacity (grav.) %f, capacity (vol.) %f" % (self.fully_charged_entry.composition.reduced_formula, self.fully_discharged_entry.composition.reduced_formula, self.get_average_voltage(), self.get_capacity_grav(), self.get_capacity_vol())


class DbConversionElectrode(ConversionElectrode):

    @staticmethod
    def from_composition_and_pd(comp, pd, working_ion_symbol="Li"):
        """
        Convenience constructor to make a ConversionElectrode from a
        composition and a phase diagram.
        Args:
            comp:
                Starting composition for ConversionElectrode, e.g.,
                Composition("FeF3")
            pd:
                A PhaseDiagram of the relevant system (e.g., Li-Fe-F)
            working_ion_symbol:
                Element symbol of working ion. Defaults to Li.
        """
        working_ion = Element(working_ion_symbol)
        entry = None
        working_ion_entry = None
        for e in pd.stable_entries:
            if e.composition.reduced_formula == comp.reduced_formula:
                entry = e
            elif e.is_element and e.composition.reduced_formula == working_ion_symbol:
                working_ion_entry = e

        if not entry:
            raise ValueError("Not stable compound found at composition {}.".format(comp))


        profile = pd.get_element_profile(working_ion, comp)
        profile.reverse() #Need to reverse because voltage goes form most charged to most discharged
        if len(profile) < 2:
            return None
        working_ion_entry = working_ion_entry
        working_ion = working_ion_entry.composition.elements[0].symbol
        normalization_els = {}
        for el, amt in comp.items():
            if el != Element(working_ion):
                normalization_els[el] = amt
        vpairs = [ConversionVoltagePair.from_steps(profile[i], profile[i + 1],
                                                   normalization_els)
                  for i in xrange(len(profile) - 1)]
        return DbConversionElectrode(vpairs, working_ion_entry, comp)

    def to_dict_summary(self, print_subelectrodes=True):
        """
        Args:
            print_subelectrodes:
                Also print data on all the possible subelectrodes
        Returns:
            a summary of this electrode"s properties in dictionary format
        """

        d = {}
        d["@module"] = self.__class__.__module__
        d["@class"] = self.__class__.__name__
        framework_comp = Composition({k: v
                                      for k, v in self._composition.items()
                                      if k.symbol != self.working_ion.symbol})

        d["framework"] = composition_to_multi_dict(framework_comp)
        d["framework_pretty"] = framework_comp.reduced_formula
        d["average_voltage"] = self.get_average_voltage()
        d["max_voltage"] = self.max_voltage
        d["min_voltage"] = self.min_voltage
        d["max_delta_volume"] = self.max_delta_volume
        d["max_instability"] = 0
        d["max_voltage_step"] = self.max_voltage_step
        d["nsteps"] = self.num_steps
        d["capacity_grav"] = self.get_capacity_grav()
        d["capacity_vol"] = self.get_capacity_vol()
        d["energy_grav"] = self.get_specific_energy()
        d["energy_vol"] = self.get_energy_density()
        d["working_ion"] = self.working_ion.symbol
        d["reactions"] = []
        d["reactant_compositions"] = []
        d["material_ids"] = []
        d["formula_id_mapping"] = {}
        comps = []
        frac = []
        for pair in self._vpairs:
            rxn = pair.rxn
            frac.append(pair.frac_charge)
            frac.append(pair.frac_discharge)
            d["reactions"].append(str(rxn))
            for i in xrange(len(rxn.coeffs)):
                if abs(rxn.coeffs[i]) > 1e-5 and rxn.all_comp[i] not in comps:
                    comps.append(rxn.all_comp[i])
                if abs(rxn.coeffs[i]) > 1e-5 and rxn.all_comp[i].reduced_formula != d["working_ion"]:
                    d["reactant_compositions"].append(rxn.all_comp[i].get_reduced_composition_and_factor()[0].to_dict)
            for e in pair.entries_charge:
                d["material_ids"].append(e.entry_id)
                d["formula_id_mapping"][e.composition.reduced_formula] = e.entry_id
            for e in pair.entries_discharge:
                d["material_ids"].append(e.entry_id)
                d["formula_id_mapping"][e.composition.reduced_formula] = e.entry_id

        d["formula_id_mapping"][self._working_ion_entry.composition.reduced_formula] = self._working_ion_entry.entry_id
        d["fracA_charge"] = min(frac)
        d["fracA_discharge"] = max(frac)
        d["material_ids"] = tuple(set(d["material_ids"]))

        d["stable_material_ids"] = d["material_ids"]
        d["unstable_material_ids"] = []

        d["nsteps"] = self.num_steps
        if print_subelectrodes:
            f_dict = lambda c: c.to_dict_summary(print_subelectrodes=False)
            d["adj_pairs"] = map(f_dict, self.get_sub_electrodes(adjacent_only=True))
            d["all_pairs"] = map(f_dict, self.get_sub_electrodes(adjacent_only=False))
        return d

    @property
    def to_dict(self):
        return self.to_dict_summary()


def composition_to_multi_dict(comp):
    """
    Given a composition, this will write out a dictionary with many 
    sub-properties for DB insertion.
    Args:
        comp:
            A Composition to turn into a dictionary
    Returns:
        A dictionary with many keys and values relating to Composition/Formula
    """
    rdict = {}
    rdict["reduced_cell_composition"] = comp.to_reduced_dict
    rdict["unit_cell_composition"] = comp.to_dict
    rdict["reduced_cell_formula"] = comp.reduced_formula
    rdict["elements"] = comp.to_dict.keys()
    rdict["nelements"] = len(comp.to_dict.keys())
    return rdict