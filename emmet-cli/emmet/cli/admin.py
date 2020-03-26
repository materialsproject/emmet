import click

from emmet.cli.utils import ensure_indexes


@click.group()
@click.pass_context
def admin(ctx):
    """administrative and utility commands"""
    pass


@admin.command()
@click.argument('fields', nargs=-1)
@click.argument('collection', nargs=1)
@click.pass_context
def index(ctx, fields, collection):
    """generate/ensure indexes on a collection"""
    coll = ctx.obj['CLIENT'].db[collection]
    created = ensure_indexes(fields, [coll])
    click.echo(f'ensured index(es) for {", ".join(fields)} on {coll.full_name}')
