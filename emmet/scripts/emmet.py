import click, os, yaml, sys, logging, operator
from collections import Counter
from pymongo import MongoClient
from pymongo.collection import ReturnDocument
from pymatgen.analysis.structure_prediction.volume_predictor import DLSVolumePredictor
from pymatgen import Structure
from fireworks import LaunchPad
from atomate.vasp.database import VaspCalcDb
from atomate.vasp.workflows.presets.core import wf_structure_optimization
from atomate.vasp.database import VaspCalcDb
from atomate.vasp.powerups import add_trackers, add_tags, add_additional_fields_to_taskdocs
from emmet.vasp.materials import group_structures, get_sg
from emmet.vasp.task_tagger import task_type
from log4mongo.handlers import MongoHandler

@click.group()
def cli():
    pass

@cli.command()
@click.option('--target_db_file', default="target.json", help='target db file')
@click.option('--tag', default=None, help='only insert tasks with specific tag')
@click.option('--insert/--no-insert', default=False, help='actually execute task addition')
def add_tasks(target_db_file, tag, insert):
    """Retrieve tasks from source and add to target"""

    exclude = {'tags': {'$ne': 'deprecated'}}

    def get_subdir(dn):
        return dn.rsplit(os.sep, 1)[-1]

    lpad = LaunchPad.auto_load()
    source = lpad.db.tasks
    print('connected to source db with', source.count(), 'tasks')

    if not os.path.exists(target_db_file):
        print(target_db_file, 'not found!')
        return
    target = VaspCalcDb.from_db_file(target_db_file, admin=True) # 'db_atomate.json'
    print('connected to target db with', target.collection.count(), 'tasks')

    ensure_indexes(['task_id', 'tags', 'dir_name'], [source, target.collection])

    tags = [tag]
    if tag is None:
        tags = [t for t in source.find(exclude).distinct('tags') if t is not None]
        print(len(tags), 'tags in source collection')

    for t in tags:

        print('### {} ###'.format(t))
        query = {'$and': [{'tags': t}, exclude]}
        source_count = source.count(query)
        print('source / target:', source_count, '/', target.collection.count(query))

        # skip tasks with task_id existing in target (have to be a string [mp-*, mvc-*])
        source_task_ids = source.find(query).distinct('task_id')
        source_mp_task_ids = [task_id for task_id in source_task_ids if isinstance(task_id, str)]
        skip_task_ids = target.collection.find({'task_id': {'$in': source_mp_task_ids}}).distinct('task_id')
        if len(skip_task_ids):
            print('skip', len(skip_task_ids), 'existing MP task ids out of', len(source_mp_task_ids))

        query.update({'task_id': {'$nin': skip_task_ids}})
        already_inserted_subdirs = [get_subdir(dn) for dn in target.collection.find(query).distinct('dir_name')]
        subdirs = [get_subdir(dn) for dn in source.find(query).distinct('dir_name') if get_subdir(dn) not in already_inserted_subdirs]
        if len(subdirs) < 1:
            continue

        print(len(subdirs), 'candidate tasks to insert')
        if not insert:
            print('add --insert flag to actually add tasks to production')
            continue

        for subdir in subdirs:
            subdir_query = {'dir_name': {'$regex': '/{}$'.format(subdir)}}
            doc = target.collection.find_one(subdir_query, {'task_id': 1})
            if doc:
                print(subdir, 'already inserted as', doc['task_id'])
                continue

            source_task_id = source.find_one(subdir_query, {'task_id': 1})['task_id']
            print('retrieve', source_task_id, 'for', subdir)
            task_doc = source.retrieve_task(source_task_id)

            if isinstance(task_doc['task_id'], int):
                c = target.db.counter.find_one_and_update({"_id": "taskid"}, {"$inc": {"c": 1}}, return_document=ReturnDocument.AFTER)["c"]
                task_doc['task_id'] = 'mp-{}'.format(c)

            target.insert_task(task_doc, use_gridfs=True)


@cli.command()
@click.argument('list_of_structures', type=click.File('rb'))
@click.option('-a', '--alt_tasks_db_file', type=click.Path(exists=True), help='config file for alternative tasks collection')
@click.option('--tag', default=None, help='only include structures with specific tag')
@click.option('--insert/--no-insert', default=False, help='actually execute workflow addition')
@click.option('--clear-logs/--no-clear-logs', default=False, help='clear MongoDB logs collection')
def add_wflows(list_of_structures, alt_tasks_db_file, tag, insert, clear_logs):
    """add workflows for list of structures / SNLs (YAML config or JSON list of pymatgen structures"""

    exclude = {'about.remarks': {'$ne': 'DEPRECATED'}}

    if not insert:
        print('DRY RUN! Add --insert flag to actually add workflows')

    try:
        snl_db_config = yaml.load(list_of_structures)
        snl_db_conn = MongoClient(snl_db_config['host'], snl_db_config['port'], j=False, connect=False)
        snl_db = snl_db_conn[snl_db_config['db']]
        snl_db.authenticate(snl_db_config['username'], snl_db_config['password'])
        snl_coll = snl_db[snl_db_config['collection']]
    except Exception as ex:
        print(ex)
        # NOTE WIP might change it to use add_snls first, and then add_wflows based on SNL collection only
        # TODO load pymatgen structures from JSON file into MongoDB collection
        # TODO also fake-tag them, add SNL info
        snl_coll = None
        print('to be implemented')
        return
    print('# SNLs:\t', snl_coll.count(exclude))

    lpad = LaunchPad.auto_load()

    logger = logging.getLogger('add_wflows')
    mongo_handler = MongoHandler(
        host=lpad.host, port=lpad.port, database_name=lpad.name, collection='add_wflows_logs',
        username=lpad.username, password=lpad.password, authentication_db=lpad.name
    )
    logger.addHandler(mongo_handler)
    ensure_indexes(['level', 'snl_id', 'formula'], [mongo_handler.collection])
    if clear_logs:
        mongo_handler.collection.drop()

    if alt_tasks_db_file is not None:
        target = VaspCalcDb.from_db_file(alt_tasks_db_file, admin=True)
        tasks_coll = target.collection
    else:
        tasks_coll = lpad.db.tasks
    print('# tasks:', tasks_coll.count())

    structure_keys = ['snl_id', 'lattice', 'sites', 'charge', 'about._materialsproject.task_id']
    NO_POTCARS = ['Po', 'At', 'Rn', 'Fr', 'Ra', 'Am', 'Cm', 'Bk', 'Cf', 'Es', 'Fm', 'Md', 'No', 'Lr']
    base_query = {'is_ordered': True, 'is_valid': True, 'nsites': {'$lt': 200}, 'sites.label': {'$nin': ['He', 'Ar', 'Ne']}} # exclude no electroneg elements
    task_base_query = {'_mpworks_meta': {'$exists': 0}}
    vp = DLSVolumePredictor()

    ensure_indexes(['snl_id', 'reduced_cell_formula', 'about.remarks', 'sites.label'], [snl_coll])

    tags = [tag]
    if tag is None:
        tags = dict(
            (t, snl_coll.count({'$and': [{'about.remarks': t}, exclude]}))
            for t in snl_coll.find(exclude).distinct('about.remarks') if t is not None
        )
        tags = sorted(tags.items(), key=operator.itemgetter(1), reverse=True)
        print(len(tags), 'tags in source collection')

    canonical_task_structures = {}
    grouped_workflow_structures = {}
    canonical_workflow_structures = {}

    for tag, ndocs in tags:
        query = {'$and': [{'about.remarks': tag}, exclude]}
        query.update(base_query)

        # TODO WIP will be removed
        if tag == 'new_ordered_icsd_2017':
            #TODO for new_ordered_icsd_2017: docs = db.icsd.find(query, {'snl': 1, 'formula_reduced_abc': 1, 'icsd_id': 1, 'elements': 1})
            print(tag, 'TODO implement db.icsd as snl_coll')
            continue
        elif tag == 'pre-atomate production':
            # TODO scan last
            continue

        print('aggregate', ndocs, 'structures for', tag, '...')
        structure_groups = snl_coll.aggregate([
            {'$match': query}, {'$group': {
                '_id': '$reduced_cell_formula',
                'structures': {'$push': dict((k.split('.')[-1], '${}'.format(k)) for k in structure_keys)}
            }}
        ], allowDiskUse=True, batchSize=50)

        print('loop formulas for', tag, '...')
        counter = Counter()
        structures, canonical_structures = {}, {}

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
                if mongo_handler.collection.find_one({'level': 'WARNING', 'formula': formula, 'snl_id': dct['snl_id']}):
                    continue # already checked
                counter['structures'] += 1
                s = Structure.from_dict(dct)
                s.snl_id = dct['snl_id']
                s.task_id = dct.get('task_id')
                s.remove_oxidation_states()
                try:
                    sgnum = get_sg(s)
                except Exception as ex:
                    s.to(fmt='json', filename='sgnum-{}.json'.format(s.snl_id))
                    print(str(ex))
                    sys.exit(0)
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
                                'formula': formula, 'snl_id': s.snl_id, 'canonical_snl_id': g[0].snl_id
                            })

            if not canonical_structures[formula]:
                continue
            #print(sum([len(x) for x in canonical_structures[formula].values()]), 'canonical structure(s) for', formula)

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

                    wf_found, readd_wf = False, False
                    if sgnum in canonical_workflow_structures[formula] and canonical_workflow_structures[formula][sgnum]:
                        for sidx, s in enumerate(canonical_workflow_structures[formula][sgnum]):
                            if structures_match(struct, s):
                                msg = 'Structure for SNL {} already added in WF {}'.format(struct.snl_id, s.fw_id)
                                print(msg)
                                if struct.task_id is not None:
                                    task_query = {'task_id': struct.task_id}
                                    task_query.update(task_base_query)
                                    task = tasks_coll.find_one(task_query, ['input.structure'])
                                    if task:
                                        s_task = Structure.from_dict(task['input']['structure'])
                                        s_task.remove_oxidation_states()
                                        if not structures_match(struct, s_task):
                                            msg = '  --> ERROR: Structure for SNL {} does not match {}'.format(struct.snl_id, struct.task_id)
                                            print(msg)
                                            logger.error(msg, extra={
                                                'formula': formula, 'snl_id': struct.snl_id, 'error': 'SNL-TASK structure mismatch'
                                            })
                                            counter['snl-task_mismatch'] += 1
                                        else:
                                            msg = '  --> OK: workflow resulted in matching task {}'.format(struct.task_id)
                                            print(msg)
                                            logger.warning(msg, extra={
                                                'formula': formula, 'snl_id': struct.snl_id, 'task_id': struct.task_id
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
                                                logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'task_id': struct.task_id})
                                                fw_found = True
                                                break
                                        if not fw_found:
                                            print('  --> no WF with enforced task-id', struct.task_id, '-> re-add workflow')
                                            readd_wf = True
                                            break
                                else:
                                    logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'fw_id': s.fw_id})
                                wf_found = True
                                break

                    if wf_found:
                        continue

                    # need to check tasks b/c not every task is guaranteed to have a workflow (e.g. VASP dir parsing)
                    if not readd_wf:
                        try:
                            if formula not in canonical_task_structures:
                                canonical_task_structures[formula] = {}
                                task_query = {'formula_pretty': formula}
                                task_query.update(task_base_query)
                                tasks = tasks_coll.find(task_query, {'input.structure': 1, 'task_id': 1, 'orig_inputs': 1})
                                if tasks.count() > 0:
                                    task_structures = {}
                                    for task in tasks:
                                        task_label = task_type(task['orig_inputs'], include_calc_type=False)
                                        if task_label == "Structure Optimization":
                                            s = Structure.from_dict(task['input']['structure'])
                                            sg = get_sg(s)
                                            if sg in canonical_structures[formula]:
                                                if sg not in task_structures:
                                                    task_structures[sg] = []
                                                s.task_id = task['task_id']
                                                task_structures[sg].append(s)
                                    if task_structures:
                                        for sg, slist in task_structures.items():
                                            canonical_task_structures[formula][sg] = [g[0] for g in group_structures(slist)]
                                        #print(sum([len(x) for x in canonical_task_structures[formula].values()]), 'canonical task structure(s) for', formula)

                            matched_task_ids = []
                            if sgnum in canonical_task_structures[formula] and canonical_task_structures[formula][sgnum]:
                                for s in canonical_task_structures[formula][sgnum]:
                                    if structures_match(struct, s):
                                        print('Structure for SNL', struct.snl_id, 'already added in task', s.task_id)
                                        matched_task_ids.append(s.task_id)
                                if struct.task_id is not None and matched_task_ids and struct.task_id not in matched_task_ids:
                                    print('  --> ERROR: task', struct.task_id, 'not in', matched_task_ids)
                                    raise ValueError
                            if matched_task_ids:
                                logger.warning('matched task ids', extra={'formula': formula, 'snl_id': struct.snl_id, 'task_id(s)': matched_task_ids})
                                continue
                        except ValueError as ex:
                            counter['unmatched_task_id'] += 1
                            continue

                    msg = 'Structure for SNL {} --> ADD WORKFLOW'.format(struct.snl_id)
                    if struct.task_id is not None:
                        msg += ' --> enforcing task-id {}'.format(struct.task_id)
                    print(msg)

                    no_potcars = set(NO_POTCARS) & set(struct.composition.elements)
                    if len(no_potcars) > 0:
                        msg = 'Structure for SNL {} --> NO POTCARS: {}'.format(struct.snl_id, no_potcars)
                        print(msg)
                        logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'no_potcars': no_potcars})
                        continue

                    try:
                        wf = wf_structure_optimization(struct, c={'ADD_MODIFY_INCAR': True})
                        wf = add_trackers(wf)
                        wf = add_tags(wf, [tag])
                        if struct.task_id is not None:
                            wf = add_additional_fields_to_taskdocs(wf, update_dict={'task_id': struct.task_id})
                        #if struct.icsd_id is not None:
                        #    wf = add_additional_fields_to_taskdocs(wf, update_dict={'icsd_id': struct.icsd_id})
                    except:
                        msg = 'Structure for SNL {} --> SKIP: Could not make workflow'.format(struct.snl_id)
                        print(msg)
                        logger.error(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'error': 'could not make workflow'})
                        continue

                    if insert:
                        old_new = lpad.add_wf(wf)
                        logger.warning('workflow added', extra={'formula': formula, 'snl_id': struct.snl_id, 'fw_id': list(old_new.values())[0]})
                    counter['add(ed)'] += 1

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
