import click

from emmet.cli.utils import get_lpad, ensure_indexes, calcdb_from_mgrant


@click.group()
def admin():
    """administrative and utility commands"""
    pass


@admin.command()
def lpad():
    """check LaunchPad configuration"""
    click.echo(get_lpad())


@admin.command()
@click.argument('fields', nargs=-1)
@click.argument('collection', nargs=1)
@click.option('-s', '--spec', help='mongogrant string for database')
def index(fields, collection, spec):
    """generate/ensure indexes on a collection"""
    if not spec:
        lpad = get_lpad()
        spec = f'{lpad.host}/{lpad.name}'

    target = calcdb_from_mgrant(spec)
    created = ensure_indexes(fields, [target.db[collection]])
    click.echo('ensured indexes for', fields, 'on', collection.full_name)
