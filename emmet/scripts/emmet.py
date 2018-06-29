import click, os, yaml, sys, logging, tarfile
from fnmatch import fnmatch
from datetime import datetime
from collections import Counter, OrderedDict
from pymongo import MongoClient
from pymongo.errors import CursorNotFound
from pymongo.collection import ReturnDocument
from pymatgen.analysis.structure_prediction.volume_predictor import DLSVolumePredictor
from pymatgen import Structure
from pymatgen.util.provenance import StructureNL, Author
from fireworks import LaunchPad
from atomate.vasp.database import VaspCalcDb
from atomate.vasp.workflows.presets.core import wf_structure_optimization
from atomate.vasp.powerups import add_trackers, add_tags, add_additional_fields_to_taskdocs
from emmet.vasp.materials import group_structures, get_sg
from emmet.vasp.task_tagger import task_type
from log4mongo.handlers import MongoHandler, MongoFormatter

if 'FW_CONFIG_FILE' not in os.environ:
    print('Please set FW_CONFIG_FILE!')
    sys.exit(0)

exclude = {'about.remarks': {'$nin': ['DEPRECATED', 'deprecated']}}
no_electroneg = ['He', 'He0+', 'Ar', 'Ar0+', 'Ne', 'Ne0+']
base_query = {'is_ordered': True, 'is_valid': True, 'nsites': {'$lt': 200}, 'sites.label': {'$nin': no_electroneg}}
task_base_query = {'tags': {'$nin': ['DEPRECATED', 'deprecated']}, '_mpworks_meta': {'$exists': 0}}
structure_keys = ['snl_id', 'lattice', 'sites', 'charge', 'about._materialsproject.task_id']

def aggregate_by_formula(coll, q, key='reduced_cell_formula'):
    query = {'$and': [q, exclude]}
    query.update(base_query)
    return coll.aggregate([
        {'$match': query}, {'$sort': OrderedDict([('nelements', 1), ('nsites', 1)])},
        {'$group': {
            '_id': '${}'.format(key),
            'structures': {'$push': dict((k.split('.')[-1], '${}'.format(k)) for k in structure_keys)}
        }}
    ], allowDiskUse=True, batchSize=1)

def get_meta_from_structure(struct):
    d = {'formula_pretty': struct.composition.reduced_formula}
    d['nelements'] = len(set(struct.composition.elements))
    d['nsites'] = len(struct)
    d['is_ordered'] = struct.is_ordered
    d['is_valid'] = struct.is_valid()
    return d

@click.group()
def cli():
    pass


@cli.command()
@click.argument('snls_db', type=click.Path(exists=True))
def ensure_meta(snls_db):
    """ensure meta-data fields are set in SNL collection"""

    snl_db_config = yaml.safe_load(open(snls_db, 'r'))
    snl_db_conn = MongoClient(snl_db_config['host'], snl_db_config['port'], j=False, connect=False)
    snl_db = snl_db_conn[snl_db_config['db']]
    snl_db.authenticate(snl_db_config['username'], snl_db_config['password'])
    snl_coll = snl_db[snl_db_config['collection']]
    print(snl_coll.count(), 'SNLs in', snl_coll.full_name)

    for idx, doc in enumerate(snl_coll.find({}, structure_keys)):
        if idx and not idx%1000:
            print(idx, '...')
        struct = Structure.from_dict(doc)
        snl_coll.update({'snl_id': doc['snl_id']}, {'$set': get_meta_from_structure(struct)})

    ensure_indexes(['snl_id', 'formula_pretty', 'nelements', 'nsites', 'is_ordered', 'is_valid'], [snl_coll])


@cli.command()
@click.argument('target_db_file', type=click.Path(exists=True))
@click.option('--tag', default=None, help='only insert tasks with specific tag')
@click.option('--insert/--no-insert', default=False, help='actually execute task addition')
def add_tasks(target_db_file, tag, insert):
    """Retrieve tasks from source and add to target"""

    if not insert:
        print('DRY RUN: add --insert flag to actually add tasks to production')

    def get_subdir(dn):
        return dn.rsplit(os.sep, 1)[-1]

    lpad = LaunchPad.auto_load()
    source = VaspCalcDb(lpad.host, lpad.port, lpad.name, 'tasks', lpad.username, lpad.password)
    print('connected to source db with', source.collection.count(), 'tasks')

    target = VaspCalcDb.from_db_file(target_db_file, admin=True)
    print('connected to target db with', target.collection.count(), 'tasks')

    ensure_indexes(['task_id', 'tags', 'dir_name', 'retired_task_id'], [source.collection, target.collection])

    tags = [tag]
    if tag is None:
        tags = [t for t in source.collection.find(exclude).distinct('tags') if t is not None]
        print(len(tags), 'tags in source collection')

    for t in tags:

        print('### {} ###'.format(t))
        query = {'$and': [{'tags': t}, exclude]}
        source_count = source.collection.count(query)
        print('source / target:', source_count, '/', target.collection.count(query))

        # skip tasks with task_id existing in target and with matching dir_name (have to be a string [mp-*, mvc-*])
        nr_source_mp_tasks, skip_task_ids = 0, []
        for doc in source.collection.find(query, ['task_id', 'dir_name']):
            if isinstance(doc['task_id'], str):
                nr_source_mp_tasks += 1
                task_query = {'task_id': doc['task_id'], '$or': [{'dir_name': doc['dir_name']}, {'_mpworks_meta': {'$exists': 0}}]}
                if target.collection.count(task_query):
                    skip_task_ids.append(doc['task_id'])
        if len(skip_task_ids):
            print('skip', len(skip_task_ids), 'existing MP task ids out of', nr_source_mp_tasks)

        query.update({'task_id': {'$nin': skip_task_ids}})
        already_inserted_subdirs = [get_subdir(dn) for dn in target.collection.find(query).distinct('dir_name')]
        subdirs = []
        for doc in source.collection.find(query, ['dir_name', 'task_id', 'retired_task_id']):
            subdir = get_subdir(doc['dir_name'])
            if subdir not in already_inserted_subdirs or 'retired_task_id' in doc:
                entry = {'subdir': subdir}
                if 'retired_task_id' in doc:
                    entry.update({'task_id': doc['task_id']})
                subdirs.append(entry)
        if len(subdirs) < 1:
            continue

        print(len(subdirs), 'candidate tasks to insert')

        for subdir_doc in subdirs:
            subdir_query = {'dir_name': {'$regex': '/{}$'.format(subdir_doc['subdir'])}}
            doc = target.collection.find_one(subdir_query, {'task_id': 1})
            if doc:
                print(subdir_doc['subdir'], 'already inserted as', doc['task_id'])
                if 'task_id' in subdir_doc and subdir_doc['task_id'] != doc['task_id']:
                    if insert:
                        target.collection.remove({'task_id': subdir_doc['task_id']})
                        target.collection.update(
                            {'task_id': doc['task_id']}, {
                                '$set': {'task_id': subdir_doc['task_id'], 'retired_task_id': doc['task_id'], 'last_updated': datetime.utcnow()},
                                '$addToSet': {'tags': t}
                            }
                        )
                    print('replaced task_id', doc['task_id'], 'with', subdir_doc['task_id'])
                continue

            source_task_id = source.collection.find_one(subdir_query, {'task_id': 1})['task_id']
            print('retrieve', source_task_id, 'for', subdir_doc['subdir'])
            task_doc = source.retrieve_task(source_task_id)

            if isinstance(task_doc['task_id'], int):
                if insert:
                    c = target.db.counter.find_one_and_update({"_id": "taskid"}, {"$inc": {"c": 1}}, return_document=ReturnDocument.AFTER)["c"]
                    task_doc['task_id'] = 'mp-{}'.format(c)
            else:
                task = target.collection.find_one({'task_id': task_doc['task_id']}, ['orig_inputs', 'output.structure'])
                if task:
                    task_label = task_type(task['orig_inputs'], include_calc_type=False)
                    if task_label == "Structure Optimization":
                        s1 = Structure.from_dict(task['output']['structure'])
                        s2 = Structure.from_dict(task_doc['output']['structure'])
                        if structures_match(s1, s2):
                            if insert:
                                target.collection.remove({'task_id': task_doc['task_id']})
                            print('INFO: removed old task!')
                        else:
                            print('ERROR: structures do not match!')
                            #json.dump({'old': s1.as_dict(), 'new': s2.as_dict()}, open('{}.json'.format(task_doc['task_id']), 'w'))
                            continue
                    else:
                        print('ERROR: not a SO task!')
                        continue

            if insert:
                target.insert_task(task_doc, use_gridfs=True)


@cli.command()
@click.option('--add_snls_db', type=click.Path(exists=True), help='config file for additional SNLs collection')
@click.option('--add_tasks_db', type=click.Path(exists=True), help='config file for additional tasks collection')
@click.option('--tag', default=None, help='only include structures with specific tag')
@click.option('--insert/--no-insert', default=False, help='actually execute workflow addition')
@click.option('--clear-logs/--no-clear-logs', default=False, help='clear MongoDB logs collection')
@click.option('--max-structures', default=1000, help='set max structures for tags to scan')
@click.option('--skip-all-scanned/--no-skip-all-scanned', default=False, help='skip all already scanned structures incl. WFs2Add/Errors')
def add_wflows(add_snls_db, add_tasks_db, tag, insert, clear_logs, max_structures, skip_all_scanned):
    """add workflows based on tags in SNL collection"""

    if not insert:
        print('DRY RUN! Add --insert flag to actually add workflows')

    lpad = LaunchPad.auto_load()

    snl_collections = [lpad.db.snls]
    if add_snls_db is not None:
        snl_db_config = yaml.safe_load(open(add_snls_db, 'r'))
        snl_db_conn = MongoClient(snl_db_config['host'], snl_db_config['port'], j=False, connect=False)
        snl_db = snl_db_conn[snl_db_config['db']]
        snl_db.authenticate(snl_db_config['username'], snl_db_config['password'])
        snl_collections.append(snl_db[snl_db_config['collection']])

    ensure_indexes(['snl_id', 'reduced_cell_formula', 'about.remarks', 'about.projects', 'sites.label', 'nsites', 'nelements'], snl_collections)
    for snl_coll in snl_collections:
        print(snl_coll.count(exclude), 'SNLs in', snl_coll.full_name)

    logger = logging.getLogger('add_wflows')
    mongo_handler = MongoHandler(
        host=lpad.host, port=lpad.port, database_name=lpad.name, collection='add_wflows_logs',
        username=lpad.username, password=lpad.password, authentication_db=lpad.name, formatter=MyMongoFormatter()
    )
    logger.addHandler(mongo_handler)
    if clear_logs:
        mongo_handler.collection.drop()
    ensure_indexes(['level', 'message', 'snl_id', 'formula', 'tags'], [mongo_handler.collection])

    tasks_collections = OrderedDict()
    tasks_collections[lpad.db.tasks.full_name] = lpad.db.tasks
    if add_tasks_db is not None: # TODO multiple alt_task_db_files?
        target = VaspCalcDb.from_db_file(add_tasks_db, admin=True)
        tasks_collections[target.collection.full_name] = target.collection
    for full_name, tasks_coll in tasks_collections.items():
        print(tasks_coll.count(), 'tasks in', full_name)

    NO_POTCARS = ['Po', 'At', 'Rn', 'Fr', 'Ra', 'Am', 'Cm', 'Bk', 'Cf', 'Es', 'Fm', 'Md', 'No', 'Lr']
    vp = DLSVolumePredictor()

    tags = OrderedDict()
    if tag is None:
        all_tags = OrderedDict()
        query = dict(exclude)
        query.update(base_query)
        for snl_coll in snl_collections:
            remarks_projects = snl_coll.distinct('about.projects', query) + snl_coll.distinct('about.remarks', query)
            for t in set(remarks_projects):
                q = {'$and': [{'$or': [{'about.remarks': t}, {'about.projects': t}]}, exclude]}
                q.update(base_query)
                if t not in all_tags:
                    all_tags[t] = [snl_coll.count(q), snl_coll]
                else:
                    print('tag -', t, '- already in', all_tags[t][-1].full_name)
        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1][0])
        for item in sorted_tags:
            to_scan = item[1][0] - lpad.db.add_wflows_logs.count({'tags': item[0]})
            if item[1][0] < max_structures and to_scan:
                tags[item[0]] = [item[1][0], to_scan, item[1][-1]]
    else:
        query = {'$and': [{'$or': [{'about.remarks': tag}, {'about.projects': tag}]}, exclude]}
        query.update(base_query)
        for snl_coll in snl_collections:
            cnt = snl_coll.count(query)
            if cnt:
                to_scan = cnt - lpad.db.add_wflows_logs.count({'tags': tag})
                tags[tag] = [cnt, to_scan, snl_coll]
                break

    if not tags:
        print('nothing to scan')
        return
    print(len(tags), 'tags to scan in source SNL collections:')
    if tag is None:
        print('[with < {} structures to scan]'.format(max_structures))
    print('\n'.join(['{} {} ({}) --> {} TO SCAN'.format(v[2].full_name, k, v[0], v[1]) for k, v in tags.items()]))

    canonical_task_structures = {}
    grouped_workflow_structures = {}
    canonical_workflow_structures = {}

    def load_canonical_task_structures(formula, full_name):
        if full_name not in canonical_task_structures:
            canonical_task_structures[full_name] = {}
        if formula not in canonical_task_structures[full_name]:
            canonical_task_structures[full_name][formula] = {}
            task_query = {'formula_pretty': formula}
            task_query.update(task_base_query)
            tasks = tasks_collections[full_name].find(task_query, {'input.structure': 1, 'task_id': 1, 'orig_inputs': 1})
            if tasks.count() > 0:
                task_structures = {}
                for task in tasks:
                    task_label = task_type(task['orig_inputs'], include_calc_type=False)
                    if task_label == "Structure Optimization":
                        s = Structure.from_dict(task['input']['structure'])
                        try:
                            sg = get_sg(s)
                        except Exception as ex:
                            s.to(fmt='json', filename='sgnum_{}.json'.format(task['task_id']))
                            msg = 'SNL {}: {}'.format(task['task_id'], ex)
                            print(msg)
                            logger.error(msg, extra={'formula': formula, 'task_id': task['task_id'], 'tags': [tag], 'error': str(ex)})
                            continue
                        if sg in canonical_structures[formula]:
                            if sg not in task_structures:
                                task_structures[sg] = []
                            s.task_id = task['task_id']
                            task_structures[sg].append(s)
                if task_structures:
                    for sg, slist in task_structures.items():
                        canonical_task_structures[full_name][formula][sg] = [g[0] for g in group_structures(slist)]
                    #print(sum([len(x) for x in canonical_task_structures[full_name][formula].values()]), 'canonical task structure(s) for', formula)

    def find_matching_canonical_task_structures(formula, struct, full_name):
        matched_task_ids = []
        if sgnum in canonical_task_structures[full_name][formula] and canonical_task_structures[full_name][formula][sgnum]:
            for s in canonical_task_structures[full_name][formula][sgnum]:
                if structures_match(struct, s):
                    print('Structure for SNL', struct.snl_id, 'already added in task', s.task_id, 'in', full_name)
                    matched_task_ids.append(s.task_id)
        return matched_task_ids


    for tag, value in tags.items():

        if tag == 'new_ordered_icsd_2017': # TODO WIP will be removed
            #TODO for new_ordered_icsd_2017: docs = db.icsd.find(query, {'snl': 1, 'formula_reduced_abc': 1, 'icsd_id': 1, 'elements': 1})
            print(tag, 'TODO implement db.icsd as snl_coll -> add_snls?')
            continue

        if skip_all_scanned and not value[1]:
            continue

        print('aggregate', value[0], 'structures for', tag, '...')
        structure_groups = aggregate_by_formula(value[-1], {'about.remarks': tag})

        print('loop formulas for', tag, '...')
        counter = Counter()
        structures, canonical_structures = {}, {}

        try:
            for idx_group, group in enumerate(structure_groups):

                counter['formulas'] += 1
                formula = group['_id']
                if formula not in structures:
                    structures[formula] = {}
                if formula not in canonical_structures:
                    canonical_structures[formula] = {}
                if idx_group and not idx_group%1000:
                    print(idx_group, '...')

                for dct in group['structures']:
                    q = {'level': 'WARNING', 'formula': formula, 'snl_id': dct['snl_id']}
                    if mongo_handler.collection.find_one(q):
                        lpad.db.add_wflows_logs.update(q, {'$addToSet': {'tags': tag}})
                        continue # already checked
                    q['level'] = 'ERROR'
                    if skip_all_scanned and mongo_handler.collection.find_one(q):
                        continue
                    mongo_handler.collection.remove(q) # avoid dups
                    counter['structures'] += 1
                    s = Structure.from_dict(dct)
                    s.snl_id = dct['snl_id']
                    s.task_id = dct.get('task_id')
                    s.remove_oxidation_states()
                    try:
                        sgnum = get_sg(s)
                    except Exception as ex:
                        s.to(fmt='json', filename='sgnum_{}.json'.format(s.snl_id))
                        msg = 'SNL {}: {}'.format(s.snl_id, ex)
                        print(msg)
                        logger.error(msg, extra={'formula': formula, 'snl_id': s.snl_id, 'tags': [tag], 'error': str(ex)})
                        continue
                    if sgnum not in structures[formula]:
                        structures[formula][sgnum] = []
                    structures[formula][sgnum].append(s)

                for sgnum, slist in structures[formula].items():
                    for g in group_structures(slist):
                        if sgnum not in canonical_structures[formula]:
                            canonical_structures[formula][sgnum] = []
                        canonical_structures[formula][sgnum].append(g[0])
                        if len(g) > 1:
                            for s in g[1:]:
                                logger.warning('duplicate structure', extra={
                                    'formula': formula, 'snl_id': s.snl_id, 'tags': [tag], 'canonical_snl_id': g[0].snl_id
                                })

                if not canonical_structures[formula]:
                    continue
                canonical_structures_list = [x for sublist in canonical_structures[formula].values() for x in sublist]

                if formula not in canonical_workflow_structures:
                    canonical_workflow_structures[formula], grouped_workflow_structures[formula] = {}, {}
                    workflows = lpad.workflows.find({'metadata.formula_pretty': formula}, {'metadata.structure': 1, 'nodes': 1, 'parent_links': 1})
                    if workflows.count() > 0:
                        workflow_structures = {}
                        for wf in workflows:
                            s = Structure.from_dict(wf['metadata']['structure'])
                            s.remove_oxidation_states()
                            sgnum = get_sg(s)
                            if sgnum in canonical_structures[formula]:
                                if sgnum not in workflow_structures:
                                    workflow_structures[sgnum] = []
                                s.fw_id = [n for n in wf['nodes'] if str(n) not in wf['parent_links']][0] # first node = SO firework
                                workflow_structures[sgnum].append(s)
                        if workflow_structures:
                            for sgnum, slist in workflow_structures.items():
                                grouped_workflow_structures[formula][sgnum] = [g for g in group_structures(slist)]
                                canonical_workflow_structures[formula][sgnum] = [g[0] for g in grouped_workflow_structures[formula][sgnum]]
                            #print(sum([len(x) for x in canonical_workflow_structures[formula].values()]), 'canonical workflow structure(s) for', formula)

                for idx_canonical, (sgnum, slist) in enumerate(canonical_structures[formula].items()):

                    for struc in slist:

                        try:
                            struct = vp.get_predicted_structure(struc)
                            struct.snl_id, struct.task_id = struc.snl_id, struc.task_id
                        except Exception as ex:
                            print('Structure for SNL', struc.snl_id, '--> VP error: use original structure!')
                            print(ex)
                            struct = struc

                        if not structures_match(struct, struc):
                            print('Structure for SNL', struc.snl_id, '--> VP mismatch: use original structure!')
                            struct = struc

                        wf_found = False
                        if sgnum in canonical_workflow_structures[formula] and canonical_workflow_structures[formula][sgnum]:
                            for sidx, s in enumerate(canonical_workflow_structures[formula][sgnum]):
                                if structures_match(struct, s):
                                    msg = 'Structure for SNL {} already added in WF {}'.format(struct.snl_id, s.fw_id)
                                    print(msg)
                                    if struct.task_id is not None:
                                        task_query = {'task_id': struct.task_id}
                                        task_query.update(task_base_query)
                                        for full_name in reversed(tasks_collections):
                                            task = tasks_collections[full_name].find_one(task_query, ['input.structure'])
                                            if task:
                                                break
                                        if task:
                                            s_task = Structure.from_dict(task['input']['structure'])
                                            s_task.remove_oxidation_states()
                                            if not structures_match(struct, s_task):
                                                msg = '  --> ERROR: Structure for SNL {} does not match {}'.format(struct.snl_id, struct.task_id)
                                                msg += '  --> CLEANUP: remove task_id from SNL'
                                                print(msg)
                                                value[-1].update({'snl_id': struct.snl_id}, {'$unset': {'about._materialsproject.task_id': 1}})
                                                logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'fw_id': s.fw_id, 'tags': [tag]})
                                                counter['snl-task_mismatch'] += 1
                                            else:
                                                msg = '  --> OK: workflow resulted in matching task {}'.format(struct.task_id)
                                                print(msg)
                                                logger.warning(msg, extra={
                                                    'formula': formula, 'snl_id': struct.snl_id, 'task_id': struct.task_id, 'tags': [tag]
                                                })
                                        else:
                                            print('  --> did not find task', struct.task_id, 'for WF', s.fw_id)
                                            fw_ids = [x.fw_id for x in grouped_workflow_structures[formula][sgnum][sidx]]
                                            fws = lpad.fireworks.find({'fw_id': {'$in': fw_ids}}, ['fw_id', 'spec._tasks'])
                                            fw_found = False
                                            for fw in fws:
                                                if fw['spec']['_tasks'][5]['additional_fields'].get('task_id') == struct.task_id:
                                                    msg = '  --> OK: workflow {} will result in intended task-id {}'.format(fw['fw_id'], struct.task_id)
                                                    print(msg)
                                                    logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'task_id': struct.task_id, 'tags': [tag]})
                                                    fw_found = True
                                                    break
                                            if not fw_found:
                                                print('  --> no WF with enforced task-id', struct.task_id)
                                                fw = lpad.fireworks.find_one({'fw_id': s.fw_id}, {'state': 1})
                                                print('  -->', s.fw_id, fw['state'])
                                                if fw['state'] == 'COMPLETED':
                                                    # the task is in lpad.db.tasks with different integer task_id
                                                    #    => find task => overwrite task_id => add_tasks will pick it up
                                                    full_name = list(tasks_collections.keys())[0]
                                                    load_canonical_task_structures(formula, full_name)
                                                    matched_task_ids = find_matching_canonical_task_structures(formula, struct, full_name)
                                                    if len(matched_task_ids) == 1:
                                                        tasks_collections[full_name].update(
                                                            {'task_id': matched_task_ids[0]}, {
                                                                '$set': {'task_id': struct.task_id, 'retired_task_id': matched_task_ids[0], 'last_updated': datetime.utcnow()},
                                                                '$addToSet': {'tags': tag}
                                                            }
                                                        )
                                                        print(' --> replaced task_id', matched_task_ids[0], 'with', struct.task_id, 'in', full_name)
                                                    elif matched_task_ids:
                                                        msg = '  --> ERROR: multiple tasks {} for completed WF {}'.format(matched_task_ids, s.fw_id)
                                                        print(msg)
                                                        logger.error(msg, extra={
                                                            'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag], 'error': 'Multiple tasks for Completed WF'
                                                        })
                                                    else:
                                                        msg = '  --> ERROR: task for completed WF {} does not exist!'.format(s.fw_id)
                                                        msg += ' --> CLEANUP: delete {} WF and re-add/run to enforce task-id {}'.format(fw['state'], struct.task_id)
                                                        print(msg)
                                                        lpad.delete_wf(s.fw_id)
                                                        break
                                                else:
                                                    print('  --> CLEANUP: delete {} WF and re-add to include task_id as additional_field'.format(fw['state']))
                                                    lpad.delete_wf(s.fw_id)
                                                    break
                                    else:
                                        logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'fw_id': s.fw_id, 'tags': [tag]})
                                    wf_found = True
                                    break

                        if wf_found:
                            continue

                        # need to check tasks b/c not every task is guaranteed to have a workflow (e.g. VASP dir parsing)
                        msg, matched_task_ids = '', OrderedDict()
                        for full_name in reversed(tasks_collections):
                            load_canonical_task_structures(formula, full_name)
                            matched_task_ids[full_name] = find_matching_canonical_task_structures(formula, struct, full_name)
                            if struct.task_id is not None and matched_task_ids[full_name] and struct.task_id not in matched_task_ids[full_name]:
                                msg = '  --> WARNING: task {} not in {}'.format(struct.task_id, matched_task_ids[full_name])
                                print(msg)
                            if matched_task_ids[full_name]:
                                break
                        if any(matched_task_ids.values()):
                            logger.warning('matched task ids' + msg, extra={
                                'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag],
                                'task_id(s)': dict((k.replace('.', '#'), v) for k, v in matched_task_ids.items())
                            })
                            continue

                        no_potcars = set(NO_POTCARS) & set(struct.composition.elements)
                        if len(no_potcars) > 0:
                            msg = 'Structure for SNL {} --> NO POTCARS: {}'.format(struct.snl_id, no_potcars)
                            print(msg)
                            logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag], 'error': no_potcars})
                            continue

                        try:
                            wf = wf_structure_optimization(struct, c={'ADD_MODIFY_INCAR': True})
                            wf = add_trackers(wf)
                            wf = add_tags(wf, [tag])
                            if struct.task_id is not None:
                                wf = add_additional_fields_to_taskdocs(wf, update_dict={'task_id': struct.task_id})
                            #if struct.icsd_id is not None:
                            #    wf = add_additional_fields_to_taskdocs(wf, update_dict={'icsd_id': struct.icsd_id})
                        except Exception as ex:
                            msg = 'Structure for SNL {} --> SKIP: Could not make workflow --> {}'.format(struct.snl_id, str(ex))
                            print(msg)
                            logger.error(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag], 'error': 'could not make workflow'})
                            continue

                        msg = 'Structure for SNL {} --> ADD WORKFLOW'.format(struct.snl_id)
                        if struct.task_id is not None:
                            msg += ' --> enforcing task-id {}'.format(struct.task_id)
                        print(msg)

                        if insert:
                            old_new = lpad.add_wf(wf)
                            logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag], 'fw_id': list(old_new.values())[0]})
                        else:
                            logger.error(msg + ' --> DRY RUN', extra={'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag]})
                        counter['add(ed)'] += 1

        except CursorNotFound as ex:
            print(ex)
            sites_elements = set([
                (len(set([e.symbol for e in x.composition.elements])), x.num_sites)
                for x in canonical_structures_list
            ])
            print(len(canonical_structures_list), 'canonical structure(s) for', formula, sites_elements)

        print(counter)


def structures_match(s1, s2):
    return bool(len(list(group_structures([s1, s2]))) == 1)

def ensure_indexes(indexes, colls):
    for index in indexes:
        for coll in colls:
           keys = [k.rsplit('_', 1)[0] for k in coll.index_information().keys()]
           if index not in keys:
               coll.ensure_index(index)
               print('ensured index', index, 'on', coll.full_name)

class MyMongoFormatter(logging.Formatter):
    KEEP_KEYS = ['timestamp', 'level', 'message', 'formula', 'snl_id', 'tags', 'error', 'canonical_snl_id', 'fw_id', 'task_id', 'task_id(s)']

    def format(self, record):
        mongoformatter = MongoFormatter()
        document = mongoformatter.format(record)
        for k in list(document.keys()):
            if k not in self.KEEP_KEYS:
                document.pop(k)
        return document


@cli.command()
@click.option('--tag', default=None, help='only include structures with specific tag')
def report(tag):
    """generate a report of calculations status"""

    lpad = LaunchPad.auto_load()
    states = ['COMPLETED', 'FIZZLED', 'READY', 'RUNNING']

    tags = [tag]
    if tag is None:
        tags = [t for t in lpad.workflows.distinct('metadata.tags') if t is not None]
        tags += [t for t in lpad.db.add_wflows_logs.distinct('tags') if t is not None and t not in tags]
        print(len(tags), 'tags in WFs and logs collections')

    from prettytable import PrettyTable
    table = PrettyTable()
    table.field_names = ['Tag', 'SNLs', 'WFs2Add', 'WFs'] + states + ['% FIZZLED', 'Progress']

    for t in tags:
        wflows = lpad.workflows.find({'metadata.tags': t}, {'state': 1})
        nr_snls = lpad.db.add_wflows_logs.count({'tags': t})
        wflows_to_add = lpad.db.add_wflows_logs.count({'tags': t, 'level': 'ERROR', 'error': {'$exists': 0}})
        counter = Counter([wf['state'] for wf in wflows])
        total = sum(v for k, v in counter.items() if k in states)
        tc, progress = t, '-'
        if wflows_to_add or counter['COMPLETED'] + counter['FIZZLED'] != total:
            tc = "\033[1;34m{}\033[0m".format(t)
            progress = (counter['COMPLETED'] + counter['FIZZLED']) / total * 100. if total else 0.
            progress = '{:.0f}%'.format(progress)
        entry = [tc, nr_snls, wflows_to_add, total] + [counter[state] for state in states]
        fizzled = counter['FIZZLED'] / total if total else 0.
        percent_fizzled = "\033[1;31m{:.0f}%\033[0m".format(fizzled*100.) \
                if fizzled > 0.2 else '{:.0f}%'.format(fizzled*100.)
        entry.append(percent_fizzled)
        entry.append(progress)
        if any(entry[2:-2]):
            table.add_row(entry)

    table.sortby = 'SNLs'
    table.reversesort = True
    table.align['Tag'] = 'r'
    print(table)


@cli.command()
@click.argument('archive', type=click.Path(exists=True))
@click.option('--add_snls_dbs', '-a', multiple=True, type=click.Path(exists=True), help='config files for additional SNLs collections')
@click.option('--insert/--no-insert', default=False, help='actually execute SNL insertion')
def add_snls(archive, add_snls_dbs, insert):
    """add structures from archive of structure files (CIF, POSCAR, ...) to (local) SNLs collection"""
    # TODO assign task_ids to structures?

    if not insert:
        print('DRY RUN! Add --insert flag to actually add SNLs')

    lpad = LaunchPad.auto_load()
    snl_collections = [lpad.db.snls]
    if add_snls_dbs:
        for add_snls_db in add_snls_dbs:
            snl_db_config = yaml.safe_load(open(add_snls_db, 'r'))
            snl_db_conn = MongoClient(snl_db_config['host'], snl_db_config['port'], j=False, connect=False)
            snl_db = snl_db_conn[snl_db_config['db']]
            snl_db.authenticate(snl_db_config['username'], snl_db_config['password'])
            snl_collections.append(snl_db[snl_db_config['collection']])
    for snl_coll in snl_collections:
        print(snl_coll.count(), 'SNLs in', snl_coll.full_name)

    fname, ext = os.path.splitext(os.path.basename(archive))
    tag, sec_ext = fname.rsplit('.', 1) if '.' in fname else [fname, '']
    if sec_ext:
        ext = ''.join([sec_ext, ext])
    exts = ['tar.gz', '.tgz']
    if ext not in exts:
        print(ext, 'not supported (yet)! Please use one of', exts)
        return

    meta_path = '{}.yaml'.format(tag)
    if not os.path.exists(meta_path):
        print('Please include meta info in', meta_path)
        return
    with open(meta_path, 'r') as f:
        meta = yaml.safe_load(f)
        meta['authors'] = [Author.parse_author(a) for a in meta['authors']]

    exclude = {'about.remarks': {'$ne': 'DEPRECATED'}}

    snls = []
    tar = tarfile.open(archive, 'r:gz')
    for member in tar.getmembers():
        if os.path.basename(member.name).startswith('.'):
            continue
        f = tar.extractfile(member)
        if f:
            contents = f.read().decode('utf-8')
            fname = member.name.lower()
            if fnmatch(fname, "*.cif*") or fnmatch(fname, "*.mcif*"):
                fmt = 'cif'
            elif fnmatch(fname, "*.json*") or fnmatch(fname, "*.mson*"):
                fmt = 'json'
            else:
                print('reading', fname, 'not supported (yet)')
                continue

            try:
                struct = Structure.from_str(contents, fmt=fmt)
            except Exception as ex:
                print(ex)
                break #continue

            formula = struct.composition.reduced_formula
            sg = get_sg(struct)
            struct_added = False

            for snl_coll in snl_collections:
                try:
                    group = aggregate_by_formula(snl_coll, {'formula_pretty': formula}, key='formula_pretty').next() # only one formula
                except StopIteration:
                    continue

                structures = []
                for dct in group['structures']:
                    s = Structure.from_dict(dct)
                    s.snl_id = dct['snl_id']
                    s.remove_oxidation_states()
                    try:
                        sgnum = get_sg(s)
                    except Exception as ex:
                        s.to(fmt='json', filename='sgnum_{}.json'.format(s.snl_id))
                        print('SNL {}: {}'.format(s.snl_id, ex))
                        continue
                    if sgnum == sg:
                        structures.append(s)

                if not structures:
                    continue

                canonical_structures = []
                for g in group_structures(structures):
                    canonical_structures.append(g[0])

                if not canonical_structures:
                    continue

                for s in canonical_structures:
                    if structures_match(struct, s):
                        print('Structure from', member.name, 'already added as SNL', s.snl_id, 'in', snl_coll.full_name)
                        struct_added = True
                        break

                if struct_added:
                    break

            if struct_added:
                continue

            print('append SNL for structure from', member.name)
            snl_dct = StructureNL(struct, meta['authors'], references=meta.get('references', '').strip(), projects=[tag]).as_dict()
            snl_dct.update(get_meta_from_structure(struct))
            prefix = snl_collections[0].database.name
            index = max([int(snl_id[len(prefix)+1:]) for snl_id in snl_collections[0].distinct('snl_id')]) + len(snls) + 1
            snl_dct['snl_id'] = '{}-{}'.format(prefix, index)
            snls.append(snl_dct)

    if snls:
        print('add', len(snls), 'SNLs')
        if insert:
            result = snl_collections[0].insert_many(snls)
            print('#SNLs inserted:', len(result.inserted_ids))
    else:
        print('no SNLs to insert')

