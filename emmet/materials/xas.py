from datetime import datetime
from itertools import groupby

import numpy as np
from scipy.interpolate import interp1d

from maggma.builder import Builder
from pydash import py_
from pymatgen import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from tqdm import tqdm


class XASAverager(Builder):
    def get_items(self):
        self.logger.info("Getting unprocessed mpids...")
        mpids = unprocessed_mpids(self.sources, self.targets)
        xas = self.sources[0]
        self.dt_fetch = datetime.utcnow()
        self.logger.info("Yielding XAS data for processing...")
        self.logger.info("{} unprocessed mpids".format(len(mpids)))
        for mp_id in tqdm(mpids):
            criteria = xas_criteria_base()
            criteria.update({'mp_id': mp_id})
            if not xas.query(criteria=criteria).count():
                raise Exception("No source docs for {}".format(mp_id))
            yield list(xas.query(criteria=criteria))

    def process_item(self, item):
        xas_docs_for_mpid = item
        mp_id = xas_docs_for_mpid[0]["mp_id"]
        if data_missing(xas_docs_for_mpid):
            return mark_invalid({"mp_id": mp_id})

        spectra = species_spectra(xas_docs_for_mpid)
        valids = [{
            "mp_id": mp_id,
            "element": element,
            "spectrum": [ary.tolist() for ary in spectrum]
        } for element, spectrum in spectra.items()]
        return [mark_valid(v) for v in valids]

    def update_targets(self, items):
        xas_averaged = self.targets[0]
        xas_averaged.ensure_index([("valid", 1), ("mp_id", 1)])
        xas_averaged.ensure_index([("mp_id", 1), ("element", 1)])
        xas_averaged.ensure_index([("chemsys", 1), ("element", 1)])
        valids, invalids = py_.partition(
            mark_lu(py_.flatten(items), xas_averaged.lu_field, self.dt_fetch),
            'valid')
        # Remove documents flagging now-valid data as invalid.
        xas_averaged.collection.delete_many(
            mark_invalid({
                "mp_id": {
                    "$in": py_.pluck(valids, 'mp_id')
                }
            }))
        bulk = xas_averaged.collection.initialize_ordered_bulk_op()
        for doc in valids:
            (bulk.find(py_.pick(doc, 'mp_id', 'element'))
                .upsert().replace_one(doc))
        for doc in invalids:
            (bulk.find(mark_invalid(py_.pick(doc, 'mp_id')))
                .upsert().replace_one(doc))
        bulk.execute()


def xas_criteria_base():
    return {'spectrum_type': 'XANES', 'edge': 'K'}


def unprocessed_mpids(sources, targets):
    xas = sources[0]
    materials = sources[1]
    xas_averaged = targets[0]
    mpids_marked_invalid = set(invalid_pks(xas_averaged, 'mp_id'))
    mpids_source_updated = set(
        updated_pks(xas, targets, 'mp_id', dt_map=lambda dt: dt.isoformat()))
    mpids_xas = xas.distinct('mp_id', criteria=xas_criteria_base())
    should = list(materials.query(
        criteria={'task_id': {'$in': mpids_xas}},
        properties={'_id': 0, 'task_id': 1, 'nelements': 1}))
    should = {(s['task_id'], s['nelements']) for s in should}
    actual = xas_averaged.collection.aggregate([
        {'$group': {'_id': '$mp_id', 'n': {'$sum': 1}}}
    ])
    actual = {(a['_id'], a['n']) for a in actual}
    mpids_build_incomplete = {s[0] for s in should - actual}
    return mpids_source_updated | (
        mpids_build_incomplete - mpids_marked_invalid)


def data_missing(xas_docs_for_mpid):
    """
    Do some sites have no spectra recorded?

    Checks symmetrically equivalent sites.
    """
    structure = Structure.from_dict(xas_docs_for_mpid[0]['structure'])
    ss = SymmSites(structure)
    absorbing_atoms = set([d['absorbing_atom'] for d in xas_docs_for_mpid])
    some_sites_absent = any(
        len(set(ss.get_equivalent_site_indices(i)) & absorbing_atoms) == 0
        for i in range(structure.num_sites))
    some_spectra_empty = any(
        len(d['spectrum']) == 0 for d in xas_docs_for_mpid)
    return some_sites_absent or some_spectra_empty


class SymmSites:
    def __init__(self, structure):
        self.structure = structure
        sa = SpacegroupAnalyzer(self.structure)
        symm_data = sa.get_symmetry_dataset()
        # equivalency mapping for the structure
        # i'th site in the input structure equivalent to eq_atoms[i]'th site
        self.eq_atoms = symm_data["equivalent_atoms"]

    def get_equivalent_site_indices(self, i):
        """
        Site indices in the structure that are equivalent to the given site i.
        """
        rv = np.argwhere(self.eq_atoms == self.eq_atoms[i]).squeeze().tolist()
        if isinstance(rv, int):
            rv = [rv]
        return rv


def species_spectra(xas_docs):
    """
    Get an equivalent-site-weighted spectrum for each specie in a structure.

    Args:
        xas_docs (list): MongoDB docs for all XAS XANES K-edge spectra
            for a structure.

    Returns:
        dict: {specie: (x, y)} a plottable (x, y) pair
            for each specie in the structure.
    """
    if not xas_docs:
        return []

    def absorbing_atom_element(d):
        site = d['structure']['sites'][d['absorbing_atom']]
        return site['species'][0]['element']

    xas_docs = sorted(xas_docs, key=absorbing_atom_element)
    spectrum = {}
    for element, group in groupby(xas_docs, absorbing_atom_element):
        spectrum[element] = site_weighted_spectrum(list(group))
    return spectrum


def site_weighted_spectrum(xas_docs, num_samples=200):
    """
    Equivalent-site-weighted spectrum for a specie in a structure.

    Args:
        xas_docs (list): MongoDB docs for all XAS XANES K-edge spectra
            for a specie for a structure.
        num_samples (int): Number of samples for interpolation.
            Original data has 100 data points.

    Returns:
        tuple: a plottable (x, y) pair for the spectrum
    """
    maxes, mins = [], []
    fs = []
    multiplicities = []

    for doc in xas_docs:
        energies = [e[0] for e in doc["spectrum"]]
        # Checking the multiplicities of sites
        s = Structure.from_dict(doc['structure'])
        sa = SpacegroupAnalyzer(s)
        ss = sa.get_symmetrized_structure()
        multiplicity = len(ss.find_equivalent_sites(s[doc['absorbing_atom']]))
        multiplicities.append(multiplicity)

        # Getting axis limits for each spectrum for the sites corresponding to
        # K-edge is a bit tricky, because the x-axis data points don't align
        # among different spectra for the same structure. So, prepare for
        # interpolation within the intersection of x-axis ranges.
        maxes.append(doc['spectrum'][-1][0])
        mins.append(doc['spectrum'][0][0])
        d0 = np.array(doc['spectrum'])
        # use 3rd-order spline interpolation for mu (idx 3) vs energy (idx 0).
        f = interp1d(
            d0[:, 0], d0[:, 3], kind='cubic', bounds_error=False, fill_value=0)
        fs.append(f)

    x_axis = np.linspace(max(mins), min(maxes), num=num_samples)
    weighted_spectrum = np.zeros(num_samples)
    sum_multiplicities = sum(multiplicities)
    for i in range(len(multiplicities)):
        weighted_spectrum += (
            multiplicities[i] * fs[i](x_axis)) / sum_multiplicities
    return (x_axis, weighted_spectrum)

# TODO: Migrate below functionality to emmet (or maggma) core / utils.

def mark_valid(doc):
    doc.update({"valid": True})
    return doc


def mark_invalid(doc):
    doc.update({"valid": False})
    return doc


def invalid_pks(target, pk):
    """Fetch values of primary key `pk` marked as invalid in target."""
    cursor = target.query(criteria=mark_invalid({}),
                          properties={'_id': 0, pk: 1})
    return py_.pluck(cursor, pk)


def updated_pks(source, targets, pk, dt_map=None):
    """Fetch primary key values that have new source data."""
    lu_targets = max([t.last_updated for t in targets])
    lu_targets = dt_map(lu_targets) if dt_map else lu_targets
    lu_filter = {source.lu_field: {'$gt': lu_targets}}
    criteria = xas_criteria_base()
    criteria.update(lu_filter)
    return source.distinct(pk, criteria=criteria)


def mark_lu(docs, lu_key, lu_val):
    """Mark documents with last-updated info."""
    return [py_.assign(d, {lu_key: lu_val}) for d in docs]
