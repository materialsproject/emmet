import click, os
from atomate.vasp.database import VaspCalcDb

@click.group()
def cli():
    pass

@cli.command()
@click.option('--source_db_file', default="source.json", help='source db file')
@click.option('--target_db_file', default="target.json", help='target db file')
@click.option('--tag', default=None, help='only insert tasks with specific tag')
@click.option('--insert/--no-insert', default=False, help='actually execute task addition')
def add_tasks(source_db_file, target_db_file, tag, insert):
    """Retrieve tasks from source and add to target"""

    def get_subdir(dn):
        return dn.rsplit(os.sep, 1)[-1]

    if not os.path.exists(source_db_file):
        print(source_db_file, 'not found!')
        return
    source = VaspCalcDb.from_db_file(source_db_file, admin=True) # '../config/db.json'
    print('connected to source db with', source.collection.count(), 'tasks')

    if not os.path.exists(target_db_file):
        print(target_db_file, 'not found!')
        return
    target = VaspCalcDb.from_db_file(target_db_file, admin=True) # 'db_atomate.json'
    print('connected to target db with', target.collection.count(), 'tasks')

    tags = [tag]
    if tag is None:
        tags = [t for t in source.collection.distinct('tags') if t is not None]
        print(len(tags), 'tags in source collection')

    for t in tags:

        print('tag:', t)
        query = {'tags': t}
        source_count = source.collection.count(query)
        print('source:', source_count, 'tasks out of', source.collection.count())
        print('target:', target.collection.count(query), 'tasks out of', target.collection.count())

        # skip tasks with task_id existing in target (have to be a string [mp-*, mvc-*])
        source_task_ids = source.collection.find(query).distinct('task_id')
        source_mp_task_ids = [task_id for task_id in source_task_ids if isinstance(task_id, str)]
        skip_task_ids = target.collection.find({'task_id': {'$in': source_mp_task_ids}}).distinct('task_id')
        print('skip', len(skip_task_ids), 'existing MP task ids out of', len(source_mp_task_ids))

        query.update({'task_id': {'$nin': skip_task_ids}})
        already_inserted_subdirs = [get_subdir(dn) for dn in target.collection.find(query).distinct('dir_name')]
        subdirs = [get_subdir(dn) for dn in source.collection.find(query).distinct('dir_name') if get_subdir(dn) not in already_inserted_subdirs]
        print(len(subdirs), 'candidate tasks to insert')
        if len(subdirs) < 1:
            continue

        if not insert:
            print('add --insert flag to actually add tasks to production')
            continue

        for subdir in subdirs:
            subdir_query = {'dir_name': {'$regex': '/{}$'.format(subdir)}}
            doc = target.collection.find_one(subdir_query, {'task_id': 1})
            if doc:
                print(subdir, 'already inserted as', doc['task_id'])
                continue

            source_task_id = source.collection.find_one(subdir_query, {'task_id': 1})['task_id']
            print('retrieve', source_task_id, 'for', subdir)
            task_doc = source.retrieve_task(source_task_id)

            if isinstance(task_doc['task_id'], int):
                c = target.db.counter.find_one_and_update({"_id": "taskid"}, {"$inc": {"c": 1}}, return_document=ReturnDocument.AFTER)["c"]
                task_doc['task_id'] = 'mp-{}'.format(c)

            target.insert_task(task_doc, use_gridfs=True)
