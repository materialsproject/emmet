import click

from pymatgen import Structure

from emmet.cli.config import structure_keys, meta_keys, snl_indexes
from emmet.cli.utils import ensure_indexes, get_meta_from_structure


@click.group()
@click.pass_context
def admin(ctx):
    """administrative and utility commands"""
    pass


def clean_ensure_indexes(dry_run, fields, coll):
    if dry_run:
        click.echo(f'Would create/ensure index(es) for {", ".join(fields)} on {coll.full_name}')
    else:
        created = ensure_indexes(fields, [coll])
        if created:
            click.echo(f'Created the following index(es) on {coll.full_name}:')
            click.echo(', '.join(created[coll.full_name]))
        else:
            click.echo('All indexes already created.')


@admin.command()
@click.argument('fields', nargs=-1)
@click.argument('collection', nargs=1)
@click.pass_context
def index(ctx, fields, collection):
    """create index(es) for fields of a collection"""
    coll = ctx.obj['CLIENT'].db[collection]
    clean_ensure_indexes(ctx.obj['DRY_RUN'], fields, coll)


@admin.command()
@click.argument('collection')
@click.pass_context
def meta(ctx, collection):
    """create meta-data fields and indexes for SNL collection"""
    coll = ctx.obj['CLIENT'].db[collection]
    q = {'$or': [{k: {'$exists': 0}} for k in meta_keys]}
    docs = coll.find(q, structure_keys)

    ndocs = docs.count()
    if ndocs > 0:
        if ctx.obj['DRY_RUN']:
            click.echo(f'Would fix meta for {ndocs} SNLs.')
        else:
            click.echo(f'Fix meta for {ndocs} SNLs ...')
            for idx, doc in enumerate(docs):
                if idx and not idx%1000:
                    click.echo(f'{idx} ...')
                struct = Structure.from_dict(doc.get('snl', doc))
                key = 'task_id' if 'task_id' in doc else 'snl_id'
                coll.update({key: doc[key]}, {'$set': get_meta_from_structure(struct)})

    clean_ensure_indexes(ctx.obj['DRY_RUN'], snl_indexes, coll)

# TODO clear logs command
#@click.option('--clear-logs/--no-clear-logs', default=False, help='clear MongoDB logs collection for specific tag')
#    if clear_logs and tag is not None:
#        mongo_handler.collection.remove({'tags': tag})

# TODO tags overview
#    TODO move collecting tags to admin?
#    tags = OrderedDict()
#    if tag is None:
#        all_tags = OrderedDict()
#        query = dict(exclude)
#        query.update(base_query)
#        for snl_coll in snl_collections:
#            print('collecting tags from', snl_coll.full_name, '...')
#            projects = snl_coll.distinct('about.projects', query)
#            remarks = snl_coll.distinct('about.remarks', query)
#            projects_remarks = projects
#            if len(remarks) < 100:
#                projects_remarks += remarks
#            else:
#                print('too many remarks in', snl_coll.full_name, '({})'.format(len(remarks)))
#            for t in set(projects_remarks):
#                q = {'$and': [{'$or': [{'about.remarks': t}, {'about.projects': t}]}, exclude]}
#                q.update(base_query)
#                if t not in all_tags:
#                    all_tags[t] = []
#                all_tags[t].append([snl_coll.count(q), snl_coll])
#        print('sort and analyze tags ...')
#        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1][0][0])
#        for item in sorted_tags:
#            total = sum([x[0] for x in item[1]])
#            q = {'tags': item[0]}
#            if not skip_all_scanned:
#                q['level'] = 'WARNING'
#            to_scan = total - lpad.db.add_wflows_logs.count(q)
#            if total < max_structures and to_scan:
#                tags[item[0]] = [total, to_scan, [x[-1] for x in item[1]]]
