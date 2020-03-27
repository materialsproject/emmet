import click

from pymatgen import Structure

from emmet.cli.config import structure_keys
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
    clean_ensure_indexes(ctx.obj['DEBUG'], fields, coll)


@admin.command()
@click.argument('collection')
@click.pass_context
def meta(ctx, collection):
    """create meta-data fields and indexes for SNL collection"""
    coll = ctx.obj['CLIENT'].db[collection]
    meta_keys = ['formula_pretty', 'nelements', 'nsites', 'is_ordered', 'is_valid']
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
                struct = Structure.from_dict(doc)
                coll.update({'snl_id': doc['snl_id']}, {'$set': get_meta_from_structure(struct)})

    fields = [
        'snl_id', 'reduced_cell_formula', 'formula_pretty', 'about.remarks', 'about.projects',
        'sites.label', 'nsites', 'nelements', 'is_ordered', 'is_valid'
    ]
    clean_ensure_indexes(ctx.obj['DEBUG'], fields, coll)
