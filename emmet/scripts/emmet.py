import click, os, yaml, sys, logging, tarfile, bson, gzip, csv, tarfile, itertools, multiprocessing, math, io, requests
from shutil import copyfile, rmtree
from glob import glob
from fnmatch import fnmatch
from datetime import datetime
from collections import Counter, OrderedDict, deque
from pymongo import MongoClient
from pymongo.errors import CursorNotFound
from pymongo.collection import ReturnDocument
from pymongo.errors import DocumentTooLarge
#from pymatgen.analysis.structure_prediction.volume_predictor import DLSVolumePredictor
from pymatgen import Structure
from pymatgen.alchemy.materials import TransformedStructure
from pymatgen.util.provenance import StructureNL, Author
from fireworks import LaunchPad, Firework
from fireworks.fw_config import FW_BLOCK_FORMAT
from atomate.vasp.database import VaspCalcDb
from atomate.vasp.drones import VaspDrone
from atomate.vasp.workflows.presets.core import wf_structure_optimization, wf_bandstructure
from atomate.vasp.powerups import add_trackers, add_tags, add_additional_fields_to_taskdocs, add_wf_metadata
from emmet.vasp.materials import group_structures, get_sg
from emmet.vasp.task_tagger import task_type
from log4mongo.handlers import MongoHandler, MongoFormatter
from prettytable import PrettyTable
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from tqdm import tqdm
from pprint import pprint
from mongogrant.client import Client

def get_lpad():
    if 'FW_CONFIG_FILE' not in os.environ:
        print('Please set FW_CONFIG_FILE!')
        sys.exit(0)
    return LaunchPad.auto_load()

exclude = {'about.remarks': {'$nin': ['DEPRECATED', 'deprecated']}}
skip_labels = ['He', 'He0+', 'Ar', 'Ar0+', 'Ne', 'Ne0+', 'D', 'D+']
base_query = {'is_ordered': True, 'is_valid': True, 'nsites': {'$lt': 200}, 'sites.label': {'$nin': skip_labels}}
task_base_query = {'tags': {'$nin': ['DEPRECATED', 'deprecated']}, '_mpworks_meta': {'$exists': 0}}
structure_keys = ['snl_id', 'lattice', 'sites', 'charge', 'about._materialsproject.task_id']
aggregation_keys = ['formula_pretty', 'reduced_cell_formula']
SCOPES = 'https://www.googleapis.com/auth/drive'
current_year = int(datetime.today().year)
year_tags = ['mp_{}'.format(y) for y in range(2018, current_year+1)]
NOMAD_OUTDIR = '/nomad/nomadlab/mpraw'
NOMAD_REPO = 'http://backend-repository-nomad.esc:8111/repo/search/calculations_oldformat?query={}'

def aggregate_by_formula(coll, q, key=None):
    query = {'$and': [q, exclude]}
    query.update(base_query)
    if key is None:
        for k in aggregation_keys:
            q = {k: {'$exists': 1}}
            q.update(base_query)
            if coll.count(q):
                key = k
                break
        else:
            raise ValueError('could not find aggregation keys', aggregation_keys, 'in', coll.full_name)
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

# a utility function to get us a slice of an iterator, as an iterator
# when working with iterators maximum lazyness is preferred
def iterator_slice(iterator, length):
    iterator = iter(iterator)
    while True:
        res = tuple(itertools.islice(iterator, length))
        if not res:
            break
        yield res

def get_subdir(dn):
    return dn.rsplit(os.sep, 1)[-1]

def get_timestamp_dir(prefix='launcher'):
    time_now = datetime.utcnow().strftime(FW_BLOCK_FORMAT)
    return '_'.join([prefix, time_now])

def contains_vasp_dirs(list_of_files):
    for f in list_of_files:
        if f.startswith("INCAR"):
            return True

def clean_path(path):
    return os.path.join(os.path.abspath(os.path.realpath(path)), '') # trailing slash

def make_block(base_path):
    block = get_timestamp_dir(prefix='block')
    block_dir = os.path.join(base_path, block)
    os.mkdir(block_dir)
    print('created', block_dir)
    return block_dir

def get_symlinked_path(root, base_path_index, insert):
    """organize directory in block_*/launcher_* via symbolic links"""
    root_split = root.split(os.sep)
    base_path = os.sep.join(root_split[:base_path_index])

    if not root_split[base_path_index].startswith('block_'):
        all_blocks = glob(os.path.join(base_path, 'block_*/'))
        if all_blocks:
            for block_dir in all_blocks:
                nr_launchers = len(glob(os.path.join(block_dir, 'launcher_*/')))
                if nr_launchers < 300:
                    break # found an existing block with < 300 launchers
            else:
                block_dir = make_block(base_path)
        else:
            block_dir = make_block(base_path)
    else:
        block_dir = os.sep.join(root_split[:base_path_index+1])

    if not root_split[-1].startswith('launcher_'):
        launch = get_timestamp_dir(prefix='launcher')
        launch_dir = os.path.join(block_dir, launch)
        if insert:
            os.rename(root, launch_dir)
            os.symlink(launch_dir, root)
        print(root, '->', launch_dir)
    else:
        launch_dir = os.path.join(block_dir, root_split[-1])
        if not os.path.exists(launch_dir):
            if insert:
                os.rename(root, launch_dir)
            print(root, '->', launch_dir)

    return launch_dir

def get_vasp_dirs(scan_path, base_path, max_dirs, insert):
    scan_path = clean_path(scan_path)
    base_path = clean_path(base_path)
    base_path_index = len(base_path.split(os.sep))-1 # account for abspath
    counter = 0

    # NOTE os.walk followlinks=False by default, as intended here
    for root, dirs, files in os.walk(scan_path):
        # TODO ignore relax1/2 subdirs if INCAR.orig found
        if contains_vasp_dirs(files):
            yield get_symlinked_path(root, base_path_index, insert)
            counter += 1
            if counter >= max_dirs:
                break
        else:
            for f in files:
                if f.endswith('.tar.gz'):
                    cwd = os.path.realpath(root)
                    path = os.path.join(cwd, f)
                    with tarfile.open(path, 'r:gz') as tf:
                        tf.extractall(cwd)
                    os.remove(path)
                    for vaspdir in get_vasp_dirs(path.replace('.tar.gz', ''), base_path, max_dirs, insert):
                        yield vaspdir
                        counter += 1
                        if counter >= max_dirs:
                            break


def parse_vasp_dirs(vaspdirs, insert, drone, already_inserted_subdirs):
    name = multiprocessing.current_process().name
    print(name, 'starting')
    lpad = get_lpad()
    target = calcdb_from_mgrant(f'{lpad.host}/{lpad.name}')
    print(name, 'connected to target db with', target.collection.count(), 'tasks')

    for vaspdir in vaspdirs:
        if get_subdir(vaspdir) in already_inserted_subdirs:
            print(name, vaspdir, 'already parsed')
            continue
        print(name, 'vaspdir:', vaspdir)

        if insert:
            try:
                for inp in ['INCAR', 'KPOINTS', 'POTCAR', 'POSCAR']:
                    input_path = os.path.join(vaspdir, inp)
                    if not glob(input_path+'.orig*'):
                        input_path = glob(input_path+'*')[0]
                        orig_path = input_path.replace(inp, inp+'.orig')
                        copyfile(input_path, orig_path)
                        print(name, 'cp', input_path, '->', orig_path)
            except Exception as ex:
                print(str(ex))
                continue

            try:
                task_doc = drone.assimilate(vaspdir)
            except Exception as ex:
                err = str(ex)
                if err == 'No VASP files found!':
                    rmtree(vaspdir)
                    print(name, 'removed', vaspdir)
                continue

            q = {'dir_name': {'$regex': get_subdir(vaspdir)}}
            # check completed_at timestamp to decide on re-parse (only relevant for --force)
            docs = list(target.collection.find(q, {'completed_at': 1}).sort([('_id', -1)]).limit(1))
            if docs and docs[0]['completed_at'] == task_doc['completed_at']:
                print('not forcing insertion of', vaspdir, '(matching completed_at timestamp)')
                continue

            # make sure that task gets the same tags as the previously parsed task (only relevant for --force)
            tags = target.collection.distinct('tags', q)
            if tags:
                print('use existing tags:', tags)
                task_doc['tags'] = tags

            if task_doc['state'] == 'successful':
                try:
                    target.insert_task(task_doc, use_gridfs=True)
                except DocumentTooLarge as ex:
                    print(name, 'remove normalmode_eigenvecs and retry ...')
                    task_doc['calcs_reversed'][0]['output'].pop('normalmode_eigenvecs')
                    try:
                        target.insert_task(task_doc, use_gridfs=True)
                    except DocumentTooLarge as ex:
                        print(name, 'also remove force_constants and retry ...')
                        task_doc['calcs_reversed'][0]['output'].pop('force_constants')
                        target.insert_task(task_doc, use_gridfs=True)

    nr_vaspdirs = len(vaspdirs)
    print(name, 'processed', nr_vaspdirs, 'VASP directories')
    return nr_vaspdirs

@click.group()
def cli():
    pass

def ensure_meta(snl_coll):
    """ensure meta-data fields and index are set in SNL collection"""

    meta_keys = ['formula_pretty', 'nelements', 'nsites', 'is_ordered', 'is_valid']
    q = {'$or': [{k: {'$exists': 0}} for k in meta_keys]}
    docs = snl_coll.find(q, structure_keys)

    if docs.count() > 0:
      print('fix meta for', docs.count(), 'SNLs ...')
      for idx, doc in enumerate(docs):
          if idx and not idx%1000:
              print(idx, '...')
          struct = Structure.from_dict(doc)
          snl_coll.update({'snl_id': doc['snl_id']}, {'$set': get_meta_from_structure(struct)})

    ensure_indexes([
      'snl_id', 'reduced_cell_formula', 'formula_pretty', 'about.remarks', 'about.projects',
      'sites.label', 'nsites', 'nelements', 'is_ordered', 'is_valid'
    ], [snl_coll])

def calcdb_from_mgrant(spec):
    client = Client()
    role = 'rw' # NOTE need write access to source to ensure indexes
    host, dbname_or_alias = spec.split('/', 1)
    auth = client.get_auth(host, dbname_or_alias, role)
    if auth is None:
        raise Exception("No valid auth credentials available!")
    return VaspCalcDb(
        auth['host'], 27017, auth['db'],
        'tasks', auth['username'], auth['password'],
        authSource=auth['db']
    )

@cli.command()
@click.argument('target_spec')
@click.option('--tag', default=None, help='only insert tasks with specific tag')
@click.option('--insert/--no-insert', default=False, help='actually execute task addition')
@click.option('--copy-snls/--no-copy-snls', default=False, help='also copy SNLs')
@click.option('--sbxn', multiple=True, help='add task to sandbox')
@click.option('--src', help='mongogrant string for source task db (overwrite default lpad)')
@click.option('--force/--no-force', default=False, help='force overwrite existing target task')
def copy(target_spec, tag, insert, copy_snls, sbxn, src, force):
    """Retrieve tasks from source and copy to target task collection (incl. SNLs if available)"""

    if not insert:
        print('DRY RUN: add --insert flag to actually add tasks to production')

    if src:
        source = calcdb_from_mgrant(src)
    else:
        lpad = get_lpad()
        source = calcdb_from_mgrant(f'{lpad.host}/{lpad.name}')
    print('connected to source db', source.collection.full_name, 'with', source.collection.count(), 'tasks')

    target = calcdb_from_mgrant(target_spec)
    print('connected to target db with', target.collection.count(), 'tasks')

    ensure_indexes(['task_id', 'tags', 'dir_name', 'retired_task_id'], [source.collection, target.collection])

    tags = [tag]
    if tag is None:
        tags = [t for t in source.collection.find(task_base_query).distinct('tags') if t is not None and t not in year_tags]
        print(len(tags), 'tags in source collection')

    # fix year tags before copying tasks
    counter = Counter()
    source_tasks = source.collection.find(
        {'$and': [{'tags': {'$in': tags}}, {'tags': {'$nin': year_tags}}]}, {'_id': 0, 'dir_name': 1}
    )
    for idx, doc in enumerate(source_tasks):
        print(idx, doc['dir_name'])
        # check whether I copied it over to production already -> add tag for previous year
        # anything not copied is tagged with the current year
        prod_task = target.collection.find_one({'dir_name': doc['dir_name']}, {'dir_name': 1, 'tags': 1})
        year_tag = year_tags[-1]
        if prod_task:
            print(prod_task['tags'])
            for t in prod_task['tags']:
                if t in year_tags:
                    year_tag = t
        r = source.collection.update({'dir_name': doc['dir_name']}, {'$addToSet': {'tags': year_tag}})
        counter[year_tag] += r['nModified']
    if counter:
        print(counter, 'year tags fixed.')

    def insert_snls(snls_list):
        if snls_list:
            print('copy', len(snls_list), 'SNLs')
            if insert:
                result = target.db.snls.insert_many(snls_list)
                print('#SNLs inserted:', len(result.inserted_ids))
            snls_list.clear()
        else:
            print('no SNLs to insert')

    table = PrettyTable()
    table.field_names = ['Tag', 'Source', 'Target', 'Skipped', 'Insert']
    sums = ['total'] + [0] * (len(table.field_names)-1)

    for t in tags:

        print('- {}'.format(t))
        row = [t]
        query = {'$and': [{'tags': t}, task_base_query]}
        source_count = source.collection.count(query)
        row += [source_count, target.collection.count(query)]

        # get list of SNLs to copy over
        # only need to check tagged SNLs in source and target; dup-check across SNL collections already done in add_snls
        # also only need to check about.projects; add_snls adds tag to about.projects and not remarks
        # TODO only need to copy if author not Materials Project!?
        if copy_snls:
            snls = lpad.db.snls.find({'about.projects': t})
            nr_snls = snls.count()
            if nr_snls:
                snls_to_copy, index, prefix = [], None, 'snl'
                for idx, doc in enumerate(snls):
                    snl = StructureNL.from_dict(doc)
                    formula = snl.structure.composition.reduced_formula
                    snl_copied = False
                    try:
                        q = {'about.projects': t, '$or': [{k: formula} for k in aggregation_keys]}
                        group = aggregate_by_formula(target.db.snls, q).next() # only one formula
                        for dct in group['structures']:
                            existing_structure = Structure.from_dict(dct)
                            if structures_match(snl.structure, existing_structure):
                                snl_copied = True
                                print('SNL', doc['snl_id'], 'already added.')
                                break
                    except StopIteration:
                        pass
                    if snl_copied:
                        continue
                    snl_dct = snl.as_dict()
                    if index is None:
                        index = max([int(snl_id[len(prefix)+1:]) for snl_id in target.db.snls.distinct('snl_id')]) + 1
                    else:
                        index += 1
                    snl_id = '{}-{}'.format(prefix, index)
                    snl_dct['snl_id'] = snl_id
                    snl_dct.update(get_meta_from_structure(snl.structure))
                    snls_to_copy.append(snl_dct)
                    if idx and not idx%100 or idx == nr_snls-1:
                        insert_snls(snls_to_copy)
            else:
                print('No SNLs available for', t)

        # skip tasks with task_id existing in target and with matching dir_name (have to be a string [mp-*, mvc-*])
        nr_source_mp_tasks, skip_task_ids = 0, []
        for doc in source.collection.find(query, ['task_id', 'dir_name']):
            if isinstance(doc['task_id'], str):
                nr_source_mp_tasks += 1
                task_query = {'task_id': doc['task_id'], '$or': [{'dir_name': doc['dir_name']}, {'_mpworks_meta': {'$exists': 0}}]}
                if target.collection.count(task_query):
                    skip_task_ids.append(doc['task_id'])
        #if len(skip_task_ids):
        #    print('skip', len(skip_task_ids), 'existing MP task ids out of', nr_source_mp_tasks)
        row.append(len(skip_task_ids))

        query.update({'task_id': {'$nin': skip_task_ids}})
        already_inserted_subdirs = [get_subdir(dn) for dn in target.collection.find(query).distinct('dir_name')]
        subdirs = []
        # NOTE make sure it's latest task if re-parse forced
        fields = ['task_id', 'retired_task_id']
        project = dict((k, True) for k in fields)
        project['subdir'] = {'$let': { # gets launcher from dir_name
            'vars': {'dir_name': {'$split': ['$dir_name', '/']}},
            'in': {'$arrayElemAt': ['$$dir_name', -1]}
        }}
        group = dict((k, {'$last': f'${k}'}) for k in fields) # based on ObjectId
        group['_id'] = '$subdir'
        group['count'] = {'$sum': 1}
        pipeline = [{'$match': query}, {'$project': project}, {'$group': group}]
        if force:
            pipeline.append({'$match': {'count': {'$gt': 1}}}) # only re-insert if duplicate parse exists
        for doc in source.collection.aggregate(pipeline):
            subdir = doc['_id']
            if force or subdir not in already_inserted_subdirs or doc.get('retired_task_id'):
                entry = dict((k, doc[k]) for k in fields)
                entry['subdir'] = subdir
                subdirs.append(entry)
        if len(subdirs) < 1:
            print('no tasks to copy.')
            continue

        row.append(len(subdirs))
        table.add_row(row)
        for idx, e in enumerate(row):
            if isinstance(e, int):
                sums[idx] += e
        #if not insert: # avoid uncessary looping
        #    continue

        for subdir_doc in subdirs:
            subdir_query = {'dir_name': {'$regex': '/{}$'.format(subdir_doc['subdir'])}}
            doc = target.collection.find_one(subdir_query, {'task_id': 1, 'completed_at': 1})

            if doc and subdir_doc.get('retired_task_id') and subdir_doc['task_id'] != doc['task_id']:
                # overwrite integer task_id (see wflows subcommand)
                # in this case, subdir_doc['task_id'] is the task_id the task *should* have
                print(subdir_doc['subdir'], 'already inserted as', doc['task_id'])
                if insert:
                    target.collection.remove({'task_id': subdir_doc['task_id']}) # remove task with wrong task_id if necessary
                    target.collection.update(
                        {'task_id': doc['task_id']}, {
                            '$set': {'task_id': subdir_doc['task_id'], 'retired_task_id': doc['task_id'], 'last_updated': datetime.utcnow()},
                            '$addToSet': {'tags': t}
                        }
                    )
                print('replace(d) task_id', doc['task_id'], 'with', subdir_doc['task_id'])
                continue

            if not force and doc:
                print(subdir_doc['subdir'], 'already inserted as', doc['task_id'])
                continue

            # NOTE make sure it's latest task if re-parse forced
            source_task_id = subdir_doc['task_id'] if force else \
                source.collection.find_one(subdir_query, {'task_id': 1})['task_id']
            print('retrieve', source_task_id, 'for', subdir_doc['subdir'])
            task_doc = source.retrieve_task(source_task_id)

            if doc: # NOTE: existing dir_name (re-parse forced)
                if task_doc['completed_at'] == doc['completed_at']:
                    print('re-parsed', subdir_doc['subdir'], 'already re-inserted into', target.collection.full_name)
                    table._rows[-1][-1] -= 1 # update Insert count in table
                    continue
                task_doc['task_id'] = doc['task_id']
                if insert:
                    target.collection.remove({'task_id': doc['task_id']}) # TODO VaspCalcDb.remove_task to also remove GridFS entries
                print('REMOVE(d) existing task', doc['task_id'])
            elif isinstance(task_doc['task_id'], int): # new task
                if insert:
                    next_tid = max([int(tid[len('mp')+1:]) for tid in target.collection.distinct('task_id')]) + 1
                    task_doc['task_id'] = 'mp-{}'.format(next_tid)
            else: # NOTE replace existing SO task with new calculation (different dir_name)
                task = target.collection.find_one({'task_id': task_doc['task_id']}, ['orig_inputs', 'output.structure'])
                if task:
                    task_label = task_type(task['orig_inputs'], include_calc_type=False)
                    if task_label == "Structure Optimization":
                        s1 = Structure.from_dict(task['output']['structure'])
                        s2 = Structure.from_dict(task_doc['output']['structure'])
                        if structures_match(s1, s2):
                            if insert:
                                target.collection.remove({'task_id': task_doc['task_id']}) # TODO VaspCalcDb.remove_task
                            print('INFO: removed old task!')
                        else:
                            print('ERROR: structures do not match!')
                            #json.dump({'old': s1.as_dict(), 'new': s2.as_dict()}, open('{}.json'.format(task_doc['task_id']), 'w'))
                            continue
                    else:
                        print('ERROR: not a SO task!')
                        continue

            if sbxn:
                task_doc['sbxn'] = list(sbxn)

            if insert:
                target.insert_task(task_doc, use_gridfs=True)

    table.align['Tag'] = 'r'
    if tag is None:
        sfmt = '\033[1;32m{}\033[0m'
        table.add_row([sfmt.format(s if s else '-') for s in sums])
    if table._rows:
        print(table)


@cli.command()
@click.argument('email')
@click.option('--add_snlcolls', '-a', type=click.Path(exists=True), help='YAML config file with multiple documents defining additional SNLs collections to scan')
@click.option('--add_tasks_db', type=click.Path(exists=True), help='config file for additional tasks collection to scan')
def find(email, add_snlcolls, add_tasks_db):
    """checks status of calculations by submitter or author email in SNLs"""
    lpad = get_lpad()

    snl_collections = [lpad.db.snls]
    if add_snlcolls is not None:
        for snl_db_config in yaml.load_all(open(add_snlcolls, 'r')):
            snl_db_conn = MongoClient(snl_db_config['host'], snl_db_config['port'], j=False, connect=False)
            snl_db = snl_db_conn[snl_db_config['db']]
            snl_db.authenticate(snl_db_config['username'], snl_db_config['password'])
            snl_collections.append(snl_db[snl_db_config['collection']])
    for snl_coll in snl_collections:
        print(snl_coll.count(exclude), 'SNLs in', snl_coll.full_name)

    tasks_collections = OrderedDict()
    tasks_collections[lpad.db.tasks.full_name] = lpad.db.tasks
    if add_tasks_db is not None: # TODO multiple alt_task_db_files?
        target = VaspCalcDb.from_db_file(add_tasks_db, admin=True)
        tasks_collections[target.collection.full_name] = target.collection
    for full_name, tasks_coll in tasks_collections.items():
        print(tasks_coll.count(), 'tasks in', full_name)

    #ensure_indexes(['snl_id', 'about.remarks', 'submitter_email', 'about.authors.email'], snl_collections)
    ensure_indexes(['snl_id', 'fw_id'], [lpad.db.add_wflows_logs])
    ensure_indexes(['fw_id'], [lpad.fireworks])
    ensure_indexes(['launch_id'], [lpad.launches])
    ensure_indexes(['dir_name', 'task_id'], tasks_collections.values())

    snl_ids = []
    query = {'$or': [{'submitter_email': email}, {'about.authors.email': email}]}
    query.update(exclude)
    for snl_coll in snl_collections:
        snl_ids.extend(snl_coll.distinct('snl_id', query))
    print(len(snl_ids), 'SNLs')

    fw_ids = lpad.db.add_wflows_logs.distinct('fw_id', {'snl_id': {'$in': snl_ids}})
    print(len(fw_ids), 'FWs')

    launch_ids = lpad.fireworks.distinct('launches', {'fw_id': {'$in': fw_ids}})
    print(len(launch_ids), 'launches')

    launches = lpad.launches.find({'launch_id': {'$in': launch_ids}}, {'launch_dir': 1})
    subdirs = [get_subdir(launch['launch_dir']) for launch in launches]
    print(len(subdirs), 'launch directories')

    for full_name, tasks_coll in tasks_collections.items():
        print(full_name)
        for subdir in subdirs:
            subdir_query = {'dir_name': {'$regex': '/{}$'.format(subdir)}}
            task = tasks_coll.find_one(subdir_query, {'task_id': 1})
            if task:
                print(task['task_id'])
            else:
                print(subdir, 'not found')

@cli.command()
@click.argument('target_db_file', type=click.Path(exists=True))
@click.option('--insert/--no-insert', default=False, help='actually execute workflow addition')
def bandstructure(target_db_file, insert):
    """add workflows for bandstructure based on materials collection"""
    lpad = get_lpad()
    source = calcdb_from_mgrant(f'{lpad.host}/{lpad.name}')
    print('connected to source db with', source.collection.count(), 'tasks')
    target = VaspCalcDb.from_db_file(target_db_file, admin=True)
    print('connected to target db with', target.collection.count(), 'tasks')
    materials = target.db["materials.core"]
    ensure_indexes(['task_id'], [materials])
    ensure_indexes(['metadata.task_id'], [lpad.workflows])
    print(materials.count(), 'core materials')

    all_mat_ids = set(materials.distinct('task_id'))
    existing_mat_ids = set(filter(None, lpad.workflows.distinct('metadata.task_id')))
    mat_ids = all_mat_ids.symmetric_difference(existing_mat_ids)
    print(len(mat_ids), 'bandstructure workflows to add')

    wflows = []
    for mat_id in mat_ids:
        structure = Structure.from_dict(materials.find_one({'task_id': mat_id}, {'structure': 1})['structure'])
        dir_name = target.collection.find_one({'task_id': mat_id}, {'dir_name': 1})['dir_name']
        subdir = get_subdir(dir_name)
        subdir_query = {'dir_name': {'$regex': '/{}$'.format(subdir)}}
        source_task = source.collection.find_one(subdir_query, {'tags': 1})
        if not source_task:
            print('source task not found -> TODO')
            break

        # bandstructure task has this year's tag (remove other year tags from source_task)
        tags = [t for t in source_task['tags'] if t not in year_tags]
        tags.append(year_tags[-1])

        wf = wf_bandstructure(structure, c={'ADD_MODIFY_INCAR': True}) # TODO non-SO bandstructure workflow -> Alex
        wf = add_trackers(wf)
        wf = add_tags(wf, tags)
        wf = add_wf_metadata(wf, structure)
        wf.metadata["task_id"] = mat_id
        wflows.append(wf)
        print(wf.as_dict())
        break

    if insert:
        lpad.bulk_add_wfs(wflows)



@cli.command()
@click.option('--add_snlcolls', '-a', multiple=True, help='mongogrant string for additional SNL collection to scan')
@click.option('--add_taskdbs', '-t', multiple=True, help='mongogrant string for additional tasks collection to scan')
@click.option('--tag', default=None, help='only include structures with specific tag')
@click.option('--insert/--no-insert', default=False, help='actually execute workflow addition')
@click.option('--clear-logs/--no-clear-logs', default=False, help='clear MongoDB logs collection for specific tag')
@click.option('--max-structures', '-m', default=1000, help='set max structures for tags to scan')
@click.option('--skip-all-scanned/--no-skip-all-scanned', default=False, help='skip all already scanned structures incl. WFs2Add/Errors')
@click.option('--force-new/--no-force-new', default=False, help='force generation of new workflow')
def wflows(add_snlcolls, add_taskdbs, tag, insert, clear_logs, max_structures, skip_all_scanned, force_new):
    """add workflows based on tags in SNL collection"""

    if not insert:
        print('DRY RUN! Add --insert flag to actually add workflows')

    lpad = get_lpad()

    client = Client()
    snl_collections = [lpad.db.snls]
    if add_snlcolls is not None:
        for snl_db_config in add_snlcolls:
            snl_db = client.db(snl_db_config)
            #snl_collections.append(snl_db['snls_underconverged']) # TODO get all snls_* in db?
            snl_collections.append(snl_db['valid_user_snls'])

    for snl_coll in snl_collections:
        ensure_meta(snl_coll)
        print(snl_coll.count(exclude), 'SNLs in', snl_coll.full_name)

    logger = logging.getLogger('add_wflows')
    mongo_handler = MongoHandler(
        host=lpad.host, port=lpad.port, database_name=lpad.name, collection='add_wflows_logs',
        username=lpad.username, password=lpad.password, authentication_db=lpad.name, formatter=MyMongoFormatter()
    )
    logger.addHandler(mongo_handler)
    if clear_logs and tag is not None:
        mongo_handler.collection.remove({'tags': tag})
    ensure_indexes(['level', 'message', 'snl_id', 'formula', 'tags'], [mongo_handler.collection])

    tasks_collections = OrderedDict()
    tasks_collections[lpad.db.tasks.full_name] = lpad.db.tasks
    if add_taskdbs is not None:
        for add_taskdb in add_taskdbs:
            target = calcdb_from_mgrant(add_taskdb)
            tasks_collections[target.collection.full_name] = target.collection
    for full_name, tasks_coll in tasks_collections.items():
        print(tasks_coll.count(), 'tasks in', full_name)

    NO_POTCARS = ['Po', 'At', 'Rn', 'Fr', 'Ra', 'Am', 'Cm', 'Bk', 'Cf', 'Es', 'Fm', 'Md', 'No', 'Lr']
    #vp = DLSVolumePredictor()

    tags = OrderedDict()
    if tag is None:
        all_tags = OrderedDict()
        query = dict(exclude)
        query.update(base_query)
        for snl_coll in snl_collections:
            print('collecting tags from', snl_coll.full_name, '...')
            projects = snl_coll.distinct('about.projects', query)
            remarks = snl_coll.distinct('about.remarks', query)
            projects_remarks = projects
            if len(remarks) < 100:
                projects_remarks += remarks
            else:
                print('too many remarks in', snl_coll.full_name, '({})'.format(len(remarks)))
            for t in set(projects_remarks):
                q = {'$and': [{'$or': [{'about.remarks': t}, {'about.projects': t}]}, exclude]}
                q.update(base_query)
                if t not in all_tags:
                    all_tags[t] = []
                all_tags[t].append([snl_coll.count(q), snl_coll])
        print('sort and analyze tags ...')
        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1][0][0])
        for item in sorted_tags:
            total = sum([x[0] for x in item[1]])
            q = {'tags': item[0]}
            if not skip_all_scanned:
                q['level'] = 'WARNING'
            to_scan = total - lpad.db.add_wflows_logs.count(q)
            if total < max_structures and to_scan:
                tags[item[0]] = [total, to_scan, [x[-1] for x in item[1]]]
    else:
        query = {'$and': [{'$or': [{'about.remarks': tag}, {'about.projects': tag}]}, exclude]}
        query.update(base_query)
        cnts = [snl_coll.count(query) for snl_coll in snl_collections]
        total = sum(cnts)
        if total:
            q = {'tags': tag}
            if not skip_all_scanned:
                q['level'] = 'WARNING'
            to_scan = total - lpad.db.add_wflows_logs.count(q)
            tags[tag] = [total, to_scan, [snl_coll for idx, snl_coll in enumerate(snl_collections) if cnts[idx]]]

    if not tags:
        print('nothing to scan')
        return
    print(len(tags), 'tags to scan in source SNL collections:')
    if tag is None:
        print('[with < {} structures to scan]'.format(max_structures))
    print('\n'.join(['{} ({}) --> {} TO SCAN'.format(k, v[0], v[1]) for k, v in tags.items()]))

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

        if skip_all_scanned and not value[1]:
            continue

        print(value[0], 'structures for', tag, '...')
        for coll in value[-1]:
            print('aggregate structures in', coll.full_name,  '...')
            structure_groups = aggregate_by_formula(coll, {'$or': [{'about.remarks': tag}, {'about.projects': tag}]})

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
                        log_entries = list(mongo_handler.collection.find(q)) # log entries for already inserted workflows
                        if log_entries:
                            if force_new:
                                q['tags'] = tag # try avoid duplicate wf insertion for same tag even if forced
                                log_entry = mongo_handler.collection.find_one(q, {'_id': 0, 'message': 1, 'canonical_snl_id': 1, 'fw_id': 1})
                                if log_entry:
                                    print('WF already inserted for SNL {} with tag {}'.format(dct['snl_id'], tag))
                                    print(log_entry)
                                    continue
                            else:
                                lpad.db.add_wflows_logs.update(q, {'$addToSet': {'tags': tag}})
                                continue # already checked
                        q = {'level': 'ERROR', 'formula': formula, 'snl_id': dct['snl_id']}
                        if skip_all_scanned and mongo_handler.collection.find_one(q):
                            lpad.db.add_wflows_logs.update(q, {'$addToSet': {'tags': tag}})
                            continue
                        mongo_handler.collection.remove(q) # avoid dups
                        counter['structures'] += 1
                        s = Structure.from_dict(dct)
                        s.snl_id = dct['snl_id']
                        s.task_id = dct.get('task_id')
                        try:
                            s.remove_oxidation_states()
                        except Exception as ex:
                            msg = 'SNL {}: {}'.format(s.snl_id, ex)
                            print(msg)
                            logger.error(msg, extra={'formula': formula, 'snl_id': s.snl_id, 'tags': [tag], 'error': str(ex)})
                            continue
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

                    if not force_new and formula not in canonical_workflow_structures:
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

                            #try:
                            #    struct = vp.get_predicted_structure(struc)
                            #    struct.snl_id, struct.task_id = struc.snl_id, struc.task_id
                            #except Exception as ex:
                            #    print('Structure for SNL', struc.snl_id, '--> VP error: use original structure!')
                            #    print(ex)
                            #    struct = struc

                            #if not structures_match(struct, struc):
                            #    print('Structure for SNL', struc.snl_id, '--> VP mismatch: use original structure!')
                            #    struct = struc
                            struct = struc

                            wf_found = False
                            if not force_new and sgnum in canonical_workflow_structures[formula] and canonical_workflow_structures[formula][sgnum]:
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
                                                    coll.update({'snl_id': struct.snl_id}, {'$unset': {'about._materialsproject.task_id': 1}})
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
                                                        logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'task_id': struct.task_id, 'fw_id': fw['fw_id'], 'tags': [tag]})
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
                            if not force_new:
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
                                wf = add_tags(wf, [tag, year_tags[-1]])
                                if struct.task_id is not None:
                                    wf = add_additional_fields_to_taskdocs(wf, update_dict={'task_id': struct.task_id})
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
                if tag is not None:
                    print('trying again ...')
                    wflows(add_snlcolls, add_tasks_db, tag, insert, clear_logs, max_structures, True)

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
@click.option('--in-progress/--no-in-progress', default=False, help='show in-progress only')
@click.option('--to-csv/--no-to-csv', default=False, help='save report as CSV')
def report(tag, in_progress, to_csv):
    """generate a report of calculations status"""

    lpad = get_lpad()
    states = Firework.STATE_RANKS
    states = sorted(states, key=states.get)

    tags = [tag]
    if tag is None:
        tags = [t for t in lpad.workflows.distinct('metadata.tags') if t is not None and t not in year_tags]
        tags += [t for t in lpad.db.add_wflows_logs.distinct('tags') if t is not None and t not in tags]
        all_tags = []
        for t in tags:
            all_tags.append((t, lpad.db.add_wflows_logs.count({'tags': t})))
        tags = [t[0] for t in sorted(all_tags, key=lambda x: x[1], reverse=True)]
        print(len(tags), 'tags in WFs and logs collections')

    table = PrettyTable()
    table.field_names = ['Tag', 'SNLs', 'WFs2Add', 'WFs'] + states + ['% FIZZLED', 'Progress']
    sums = ['total'] + [0] * (len(table.field_names)-1)

    for t in tags:
        wflows = lpad.workflows.find({'metadata.tags': t}, {'state': 1})
        nr_snls = lpad.db.add_wflows_logs.count({'tags': t})
        wflows_to_add = lpad.db.add_wflows_logs.count({'tags': t, 'level': 'ERROR', 'error': {'$exists': 0}})
        counter = Counter([wf['state'] for wf in wflows])
        total = sum(v for k, v in counter.items() if k in states)
        tc, progress = t, '-'
        if wflows_to_add or counter['COMPLETED'] + counter['FIZZLED'] != total:
            tc = "\033[1;34m{}\033[0m".format(t) if not to_csv else t
            progress = (counter['COMPLETED'] + counter['FIZZLED']) / total * 100. if total else 0.
            progress = '{:.0f}%'.format(progress)
        elif in_progress:
            continue
        entry = [tc, nr_snls, wflows_to_add, total] + [counter[state] for state in states]
        fizzled = counter['FIZZLED'] / total if total else 0.
        if progress != '-' and bool(counter['COMPLETED'] + counter['FIZZLED']):
            fizzled = counter['FIZZLED'] / (counter['COMPLETED'] + counter['FIZZLED'])
        sfmt = "\033[1;31m{:.0f}%\033[0m" if (not to_csv and fizzled > 0.2) else '{:.0f}%'
        percent_fizzled = sfmt.format(fizzled*100.)
        entry.append(percent_fizzled)
        entry.append(progress)
        for idx, e in enumerate(entry):
            if isinstance(e, int):
                sums[idx] += e
        if any(entry[2:-2]):
            table.add_row(entry)

    if tag is None:
        sfmt = '{}' if to_csv else '\033[1;32m{}\033[0m'
        table.add_row([sfmt.format(s if s else '-') for s in sums])
    table.align['Tag'] = 'r'
    print(table)

    if to_csv:
        with open('emmet_report.csv', 'w') as csv_file:
            writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(table._field_names)
            options = table._get_options({})
            for row in table._get_rows(options):
                writer.writerow(row)


@cli.command()
@click.argument('archive', type=click.Path(exists=True))
@click.option('--add_snlcolls', '-a', type=click.Path(exists=True), help='YAML config file with multiple documents defining additional SNLs collections to check against')
@click.option('--insert/--no-insert', default=False, help='actually execute SNL insertion')
def load(archive, add_snlcolls, insert):
    """add structures from archive of structure files (CIF, POSCAR, ...) to (local) SNLs collection"""
    # TODO assign task_ids to structures?

    if not insert:
        print('DRY RUN! Add --insert flag to actually add SNLs')

    fname, ext = os.path.splitext(os.path.basename(archive))
    tag, sec_ext = fname.rsplit('.', 1) if '.' in fname else [fname, '']
    if sec_ext:
        ext = ''.join([sec_ext, ext])
    exts = ['tar.gz', '.tgz', 'bson.gz']
    if ext not in exts:
        print(ext, 'not supported (yet)! Please use one of', exts)
        return

    input_structures = []
    if ext == 'bson.gz':
        for idx, doc in enumerate(bson.decode_file_iter(gzip.open(archive))):
            if idx and not idx%1000:
                print(idx, '...')
            elements = set([specie['element'] for site in doc['structure']['sites'] for specie in site['species']])
            if any([bool(l in elements) for l in skip_labels]):
                continue
            input_structures.append(TransformedStructure.from_dict(doc['structure']))
    else:
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
                    input_structures.append(Structure.from_str(contents, fmt=fmt))
                except Exception as ex:
                    print(ex)
                    break #continue

    print(len(input_structures), 'structure(s) loaded.')
    add_snls(tag, input_structures, add_snlcolls, insert)


def add_snls(tag, input_structures, add_snlcolls, insert):
    """add structures to (local) SNLs collection"""

    meta_path = '{}.yaml'.format(tag)
    meta = None
    if not os.path.exists(meta_path):
        meta = {'authors': ['Materials Project <feedback@materialsproject.org>']}
        print(meta_path, 'not found. Using', meta)
    else:
        with open(meta_path, 'r') as f:
            meta = yaml.safe_load(f)
    meta['authors'] = [Author.parse_author(a) for a in meta['authors']]

    lpad = get_lpad()
    snl_collections = [lpad.db.snls]
    if add_snlcolls is not None:
        for snl_db_config in yaml.load_all(open(add_snlcolls, 'r')):
            snl_db_conn = MongoClient(snl_db_config['host'], snl_db_config['port'], j=False, connect=False)
            snl_db = snl_db_conn[snl_db_config['db']]
            snl_db.authenticate(snl_db_config['username'], snl_db_config['password'])
            snl_collections.append(snl_db[snl_db_config['collection']])
    for snl_coll in snl_collections:
        print(snl_coll.count(), 'SNLs in', snl_coll.full_name)

    def insert_snls(snls_list):
        if snls_list:
            print('add', len(snls_list), 'SNLs')
            if insert:
                result = snl_collections[0].insert_many(snls_list)
                print('#SNLs inserted:', len(result.inserted_ids))
            snls_list.clear()
        else:
            print('no SNLs to insert')

    snls, index = [], None
    for idx, istruct in enumerate(input_structures):

        struct = istruct.final_structure if isinstance(istruct, TransformedStructure) else istruct
        formula = struct.composition.reduced_formula
        try:
            sg = get_sg(struct)
        except Exception as ex:
            struct.to(fmt='json', filename='sgnum_{}_{}.json'.format(tag, formula))
            print('Structure for {}: {}'.format(formula, ex))
            continue
        if not (struct.is_ordered and struct.is_valid()):
            print('Structure for', formula, sg, 'not ordered and valid!')
            continue
        try:
            struct.remove_oxidation_states()
        except Exception as ex:
            print(struct.sites)
            print(ex)
            print('Structure for', formula, sg, 'error in remove_oxidation_states!')
            sys.exit(0) #continue

        struct_added = False
        for snl_coll in snl_collections:
            try:
                q = {'$or': [{k: formula} for k in aggregation_keys]}
                group = aggregate_by_formula(snl_coll, q).next() # only one formula
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
                    print('Structure for', formula, sg, 'already added as SNL', s.snl_id, 'in', snl_coll.full_name)
                    struct_added = True
                    break

            if struct_added:
                break

        if struct_added:
            continue

        prefix = snl_collections[0].database.name
        if index is None:
            index = max([int(snl_id[len(prefix)+1:]) for snl_id in snl_collections[0].distinct('snl_id')]) + 1
        else:
            index += 1
        snl_id = '{}-{}'.format(prefix, index)
        print('append SNL for structure with', formula, sg, 'as', snl_id)
        references = meta.get('references', '').strip()
        if isinstance(istruct, TransformedStructure):
            snl = istruct.to_snl(meta['authors'], references=references, projects=[tag])
        else:
            snl = StructureNL(istruct, meta['authors'], references=references, projects=[tag])
        snl_dct = snl.as_dict()
        snl_dct.update(get_meta_from_structure(struct))
        snl_dct['snl_id'] = snl_id
        snls.append(snl_dct)

        if idx and not idx%100 or idx == len(input_structures)-1:
            insert_snls(snls)


@cli.command()
@click.argument('base_path', type=click.Path(exists=True))
@click.option('--insert/--no-insert', default=False, help='actually execute task insertion')
@click.option('--nproc', '-n', type=int, default=1, help='number of processes for parallel parsing')
@click.option('--max-dirs', '-m', type=int, default=10, help='maximum number of directories to parse')
@click.option('--force/--no-force', default=False, help='force re-parsing of task')
#@click.option('--add_snlcolls', '-a', type=click.Path(exists=True), help='YAML config file with multiple documents defining additional SNLs collections to scan')
#@click.option('--make-snls/--no-make-snls', default=False, help='also create SNLs for parsed tasks')
def parse(base_path, insert, nproc, max_dirs, force):#, add_snlcolls, make_snls):
    """parse VASP output directories in base_path into tasks and tag"""
    if not insert:
        print('DRY RUN: add --insert flag to actually insert tasks')

    lpad = get_lpad()
    target = calcdb_from_mgrant(f'{lpad.host}/{lpad.name}')
    print('connected to target db with', target.collection.count(), 'tasks')
    base_path = os.path.join(base_path, '')
    base_path_split = base_path.split(os.sep)
    tag = base_path_split[-1] if base_path_split[-1] else base_path_split[-2]
    drone = VaspDrone(parse_dos='auto', additional_fields={'tags': [tag, year_tags[-1]]})
    already_inserted_subdirs = [get_subdir(dn) for dn in target.collection.find({'tags': tag}).distinct('dir_name')]
    print(len(already_inserted_subdirs), 'unique VASP directories already inserted for', tag)
    if force:
        already_inserted_subdirs = []
        print('FORCING directory re-parse and overriding tasks!')

    chunk_size = math.ceil(max_dirs/nproc)
    if nproc > 1 and max_dirs <= chunk_size:
        nproc = 1
        print('max_dirs =', max_dirs, 'but chunk size =', chunk_size, '-> parsing sequentially')

    pool = multiprocessing.Pool(processes=nproc)
    iterator_vaspdirs = get_vasp_dirs(base_path, base_path, max_dirs, insert)
    iterator = iterator_slice(iterator_vaspdirs, chunk_size) # process in chunks
    queue = deque()
    total_nr_vaspdirs_parsed = 0

    while iterator or queue:
        try:
            args = [next(iterator), insert, drone, already_inserted_subdirs]
            queue.append(pool.apply_async(parse_vasp_dirs, args))
        except (StopIteration, TypeError):
            iterator = None
        while queue and (len(queue) >= pool._processes or not iterator):
            process = queue.pop()
            process.wait(1)
            if not process.ready():
                queue.append(process)
            else:
                total_nr_vaspdirs_parsed += process.get()

    pool.close()
    print('DONE:', total_nr_vaspdirs_parsed, 'parsed')

    #input_structures = []
    #                if make_snls:
    #                    s = Structure.from_dict(task_doc['input']['structure'])
    #                    input_structures.append(s)

    #if insert and make_snls:
    #    print('add SNLs for', len(input_structures), 'structures')
    #    add_snls(tag, input_structures, add_snlcolls, insert)

def upload_archive(path, name, service, parent=None):
    media = MediaFileUpload(path, mimetype='application/gzip', resumable=True)
    body = {'name': name, 'parents': [parent]}
    request = service.files().create(media_body=media, body=body)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print("Uploaded %d%%." % int(status.progress() * 100))
    print("Upload Complete!")

def download_file(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    with tqdm(total=100) as pbar:
        while done is False:
            status, done = downloader.next_chunk()
            pbar.update(int(status.progress() * 100))
    return fh.getvalue()

@cli.command()
@click.argument('target_spec')
@click.option('--block-filter', '-f', help='block filter substring (e.g. block_2017-)')
@click.option('--sync-nomad/--no-sync-nomad', default=False, help='sync to NoMaD repository')
def gdrive(target_spec, block_filter, sync_nomad):
    """sync launch directories for target task DB to Google Drive"""
    target = calcdb_from_mgrant(target_spec)
    print('connected to target db with', target.collection.count(), 'tasks')
    print(target.db.materials.count(), 'materials')

    creds, store = None, None
    if os.path.exists('token.json'):
        store = file.Storage('token.json')
        creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
        store = file.Storage('token.json')
        creds = tools.run_flow(flow, store)
    service = build('drive', 'v3', http=creds.authorize(Http()))
    garden_id = os.environ.get('MPDRIVE_GARDEN_ID')
    if not garden_id:
        print('MPDRIVE_GARDEN_ID not set!')
        return

    launcher_paths = []
    full_launcher_path = []

    def recurse(service, folder_id):
        page_token = None
        query = "'{}' in parents".format(folder_id)
        while True:
            response = service.files().list(
                q=query, spaces='drive', pageToken=page_token,
                fields='nextPageToken, files(id, name, modifiedTime, size)',
            ).execute()

            for launcher in response['files']:
                if '.json' not in launcher['name']:
                    if '.tar.gz' in launcher['name']:
                        launcher_name = launcher['name'].replace('.tar.gz', '')
                        full_launcher_path.append(launcher_name)
                        launcher_paths.append(os.path.join(*full_launcher_path))
                        if sync_nomad:
                            #nomad_query='alltarget repository_filepaths.split="{}"'.format(','.join(full_launcher_path))
                            nomad_query='alltarget repository_filepaths.split="{}"'.format(full_launcher_path[-1])
                            print(nomad_query)
                            resp = requests.get(NOMAD_REPO.format(nomad_query)).json()
                            if 'meta' in resp:
                                path = launcher_paths[-1] + '.tar.gz'
                                if resp['meta']['total_hits'] < 1: # calculation not found in NoMaD repo
                                    print('Retrieve', path, '...')
                                    if not os.path.exists(path):
                                        outdir = os.path.join(*full_launcher_path[:-1])
                                        if not os.path.exists(outdir):
                                            os.makedirs(outdir)
                                        content = download_file(service, launcher['id'])
                                        with open(path, 'wb') as f:
                                            f.write(content)
                                        print('... DONE.')
                                    else:
                                        print('... ALREADY DOWNLOADED.')
                                else:
                                    print(path, 'found in NoMaD repo:')
                                    #pprint(resp)
                                    for d in resp['data']:
                                        print('\t', d['attributes']['repository_archive_gid'])
                                    sys.exit(0)
                            else:
                                raise Exception(resp['errors'][0]['detail'])
                    else:
                        full_launcher_path.append(launcher['name'])
                        recurse(service, launcher['id'])

                    del full_launcher_path[-1:]

            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break # done with launchers in current block


    # TODO older launcher directories don't have prefix
    # TODO also cover non-b/l hierarchy
    block_page_token = None
    block_query = "'{}' in parents".format(garden_id) if block_filter is None \
        else "'{}' in parents and name contains '{}'".format(garden_id, block_filter)

    while True:
        block_response = service.files().list(
            q=block_query, spaces='drive', pageToken=block_page_token,
            fields='nextPageToken, files(id, name)'
        ).execute()

        for block in block_response['files']:
            print(block['name'])
            full_launcher_path.clear()
            full_launcher_path.append(block['name'])
            recurse(service, block['id'])

        block_page_token = block_response.get('nextPageToken', None)
        if block_page_token is None:
            break # done with blocks

    launcher_paths.sort()
    print(len(launcher_paths), 'launcher directories in GDrive')

    if sync_nomad:
        return

    query = {}
    blessed_task_ids = [
        task_id for doc in target.db.materials.find(query, {'task_id': 1, 'blessed_tasks': 1})
        for task_type, task_id in doc['blessed_tasks'].items()
    ]
    print(len(blessed_task_ids), 'blessed tasks.')

    nr_launchers_sync = 0
    outfile = open('launcher_paths_{}.txt'.format(block_filter), 'w')
    splits = ['block_', 'res_1_aflow_engines-', 'aflow_engines-']
    for task in target.collection.find({'task_id': {'$in': blessed_task_ids}}, {'dir_name': 1}):
        dir_name = task['dir_name']
        for s in splits:
            ds = dir_name.split(s)
            if len(ds) == 2:
                block_launcher = s + ds[-1]
                if block_launcher not in launcher_paths and (
                    block_filter is None or \
                    (block_filter is not None and block_launcher.startswith(block_filter))
                ):
                    nr_launchers_sync += 1
                    outfile.write(block_launcher + '\n')
                break
        else:
            print('could not split', dir_name)
            return

    outfile.close()
    print(nr_launchers_sync, 'launchers to sync')
    return

    nr_tasks_processed = 0
    prev = None
    outfile = open('launcher_paths.txt', 'w')
    stage_dir = '/project/projectdirs/matgen/garden/rclone_to_mp_drive'


    for idx, dir_name in enumerate(dir_names):
        block_launcher_split = dir_name.split(os.sep)
        #if prev is not None and prev != block_launcher_split[0]: # TODO remove
        #    break
        print(idx, dir_name)
        archive_name = '{}.tar.gz'.format(block_launcher_split[-1])
        query = "name = '{}'".format(archive_name)
        response = service.files().list(
            q=query, spaces='drive', fields='files(id, name, size, parents)'
        ).execute()
        files = response['files']
        archive_path = os.path.join(stage_dir, dir_name + '.tar.gz')
        if files:
            if len(files) > 1:
                # duplicate uploads - delete all and re-upload
                for f in files:
                  print('removing', f['name'], '...')
                  service.files().delete(fileId=f['id']).execute()
                print('TODO: rerun to upload!')
            elif int(files[0]['size']) < 50:
                service.files().delete(fileId=files[0]['id']).execute()
                if os.path.exists(archive_path):
                    parent = files[0]['parents'][0]
                    upload_archive(archive_path, archive_name, service, parent=parent)
                else:
                    print('TODO: get from HPSS')
                    outfile.write(dir_name + '\n')
            else:
                print('OK:', files[0])
        else:
            if os.path.exists(archive_path):
                # make directories
                parents = [garden_id]
                for folder in block_launcher_split[:-1]:
                    query = "name = '{}'".format(folder)
                    response = service.files().list(
                        q=query, spaces='drive', fields='files(id, name)', pageSize=1
                    ).execute()
                    if not response['files']:
                        print('create dir ...', folder)
                        body = {
                          'name': folder,
                          'mimeType': "application/vnd.google-apps.folder",
                          'parents': [parents[-1]]
                        }
                        gdrive_folder = service.files().create(body=body).execute()
                        parents.append(gdrive_folder['id'])
                    else:
                        parents.append(response['files'][0]['id'])

                upload_archive(archive_path, archive_name, service, parent=parents[-1])
            else:
                print('TODO: get from HPSS')
                outfile.write(dir_name + '\n')
        nr_tasks_processed += 1
        prev = block_launcher_split[0]

    print(nr_tasks_processed)
    outfile.close()
