import click

from emmet.cli.utils import get_lpad

@click.group()
def admin():
    """administrative and utility commands"""
    pass

@admin.command()
def lpad():
    """check LaunchPad configuration"""
    try:
        print(get_lpad())
    except ValueError as ex:
        print(ex)
