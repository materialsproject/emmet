exclude = {'about.remarks': {
    '$nin': ['DEPRECATED', 'deprecated']
}}
skip_labels = ['He', 'He0+', 'Ar', 'Ar0+', 'Ne', 'Ne0+', 'D', 'D+', 'T', 'M']
base_query = {
    'is_ordered': True, 'is_valid': True, 'nsites': {'$lt': 200}, '$or': [
        {'sites.label': {'$nin': skip_labels}},
        {'snl.sites.label': {'$nin': skip_labels}}
    ]
}
task_base_query = {
    'tags': {'$nin': ['DEPRECATED', 'deprecated']},
    '_mpworks_meta': {'$exists': 0}
}
aggregation_keys = ['formula_pretty', 'reduced_cell_formula']
meta_keys = ['formula_pretty', 'nelements', 'nsites', 'is_ordered', 'is_valid']
structure_keys = [
    'snl_id', 'task_id', 'lattice', 'sites', 'charge', 'about._materialsproject.task_id',
    'snl.lattice', 'snl.sites', 'snl.charge', 'snl.about._materialsproject.task_id'
]
NO_POTCARS = [
    'Po', 'At', 'Rn', 'Fr', 'Ra', 'Am', 'Cm',
    'Bk', 'Cf', 'Es', 'Fm', 'Md', 'No', 'Lr'
]
snl_indexes = [
    'snl_id', 'task_id', 'reduced_cell_formula', 'formula_pretty',
    'nsites', 'nelements', 'is_ordered', 'is_valid',
    'about.remarks', 'about.projects', 'sites.label',
    'snl.about.remarks', 'snl.about.projects', 'snl.sites.label'
]
