import numpy as np
from pymatgen.ext.matproj import MPRester
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from typing import List


def unpack(query, d):
    if not query:
        return d
    if isinstance(d, List):
        return unpack(query[1:], d.__getitem__(int(query.pop(0))))
    return unpack(query[1:], d.__getitem__(query.pop(0)))


# TODO Move polaron compare to a different function to make validation easier
# TODO Matching should have have an easier way of setting distance tolerance
    # can't this all be done inside of structure matcher to find mapping or something?
def matcher(bulk_struc, defect_struc, final_bulk_struc=None, final_defect_struc=None):
    matching_indices = []
    dis = []

    for j in range(len(defect_struc)):
        for i in range(len(bulk_struc)):
            if (
                    bulk_struc[i].species == defect_struc[j].species
                    and bulk_struc[i].distance(defect_struc[j]) < .02
                    and bulk_struc[i].properties.get('ghost', False) == defect_struc[j].properties.get('ghost', False)
            ):
                matching_indices.append((i, j))
                dis.append(j)
                break

    def_index = list(set(range(len(defect_struc))).difference(set(dis)))

    # Consider a possible polaron
    if len(def_index) == 0:
        matching_indices = []

        for j in range(len(defect_struc)):
            for i in range(len(bulk_struc)):
                if (
                        bulk_struc[i].specie.as_dict().get('element') == defect_struc[j].specie.as_dict().get('element')
                        and bulk_struc[i].distance(defect_struc[j]) < .02
                        and bulk_struc[i].properties.get('ghost', False) == defect_struc[j].properties.get('ghost',
                                                                                                           False)):
                    matching_indices.append((i, j))
                    break

        oxi_diff = [abs(final_defect_struc[d].specie.oxi_state - final_bulk_struc[b].specie.oxi_state) for b, d in matching_indices]
        def_index = np.argmax(oxi_diff)
        matching_indices.pop(def_index)
        return def_index, matching_indices

    elif len(def_index) > 1:
        print(def_index)
        raise ValueError("The provided defect structure and bulk structure "
                         "have more than one potential defect site")

    return def_index[0], matching_indices


def get_dielectric(mpid):
    with MPRester() as mp:
        dat = mp.get_data(mpid, prop='diel')
        band_gap = mp.get_data(mpid, prop='band_gap')[0]['band_gap']
    if band_gap == 0.0:
        return np.inf
    try:
        return dat[0]['diel']['e_total']
    except:
        return None


from copy import deepcopy


def get_mpid(s):
    struc = deepcopy(s)
    struc.remove_oxidation_states()
    struc.remove_spin()
    for p in struc.site_properties:
        struc.remove_site_property(p)
    sga = SpacegroupAnalyzer(struc)
    with MPRester() as mp:
        dat = mp.query(
            criteria={
                'chemsys': struc.composition.chemical_system,
                'spacegroup.symbol': sga.get_space_group_symbol()
            },
            properties=['material_id', 'formation_energy_per_atom']
        )

    dat.sort(key=lambda x: x['formation_energy_per_atom'])
    try:
        return dat[0]['material_id']
    except:
        return None
