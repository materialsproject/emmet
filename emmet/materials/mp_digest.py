from maggma.builder import Builder
from pydash.objects import get


class DigestBuilder(Builder):
    """
    A builder for Materials Project book-keeping. A summary of important
    data from the mp_website collection so changes can be tracked.
    """
    # TODO: reach consensus on what should be included here

    def __init__(self, mp_website, digest,
                 query=None, **kwargs):

        self.mp_website = mp_website
        self.digest = digest
        self.query = query or {}

        super().__init__(sources=[mp_website],
                         targets=[digest],
                         **kwargs)

    def get_items(self):

        materials = self.mp_website.query(criteria=self.query,
                                          properties=[
                                              'task_id',
                                              'task_ids',
                                              'blessed_tasks',
                                              'volume',
                                              'density',
                                              'nelements',
                                              'nsites',
                                              'e_above_hull',
                                              'band_gap',
                                              'spacegroup',
                                              'sbxn',
                                              'elasticity',
                                              'has',
                                              'has_bandstrcucture',
                                              'magnetic_type',
                                              'total_magnetization',
                                              'last_updated'
                                          ])
        self.total = materials.count()
        self.logger.info("Found {} materials".format(self.total))
        date = datetime.datetime.now()
        source = ("{}:{}/{}".format(self.mp_website.host,
                                    self.mp_website.port,
                                    self.mp_website.database),
                  self.mp_website.collection_name)

        for material in materials:
            yield (material, date, source)

    def process_item(self, item):

        material, date, source = item

        has = material.get('has', [])
        # as far as I can tell, 'has' is a new key so not always present
        if material.get('has_bandstructure', False):
            if 'bandstructure' not in has:
                has.append('bandstructure')

        return {
            'digest_date': date,
            'source': source,
            'task_id': material['task_id'],
            'task_ids': get(material, 'task_ids', []),
            'blessed_tasks': get(material, 'blessed_tasks', []),
            'volume': get(material, 'volume'),
            'density': get(material, 'density'),
            'nelements': get(material, 'nelements'),
            'nsites': get(material, 'nsites'),
            'e_above_hull': get(material, 'e_above_hull'),
            'band_gap': get(material, 'band_gap.search_gap.band_gap', {}),
            'spacegroup': get(material, 'spacegroup.number'),
            'sbxn': get(material, 'sbxn'),
            'bulk_modulus': get(material, 'elasticity.K_VRH', {}),
            'magnetic_type': get(material, 'magnetic_type'),
            'total_magnetization': get(material, 'total_magnetization', None),
            'has': has,
            'material_last_updated': get(material, 'last_updated')
        }

    def update_targets(self, items):
        self.digest.update(docs=items, key=['task_id'])
