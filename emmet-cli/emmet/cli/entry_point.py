import logging
import os
from io import StringIO

import click
from github3 import GitHub
from github3.session import GitHubSession

from emmet.cli.admin import admin
from emmet.cli.calc import calc
from emmet.cli.tasks import tasks
from emmet.cli.utils import EmmetCliError, StorageGateway

logger = logging.getLogger("")
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


def opt_prompt():
    return click.prompt("GitHub OPT", hide_input=True)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "--spec-or-dbfile",
    metavar="HOST/DB",
    help="MongoGrant spec or path to db.json for DB to use.",
)
@click.option("--run", is_flag=True, help="Run DB/filesystem write operations.")
@click.option("--issue", type=int, help="Production tracker issue (required if --run).")
@click.option("--sbatch", is_flag=True, help="Switch to SBatch mode.")
@click.option(
    "--ntries",
    default=1,
    show_default=True,
    help="Number of jobs (for walltime > 48h).",
)
@click.option("--bb", is_flag=True, help="Use burst buffer.")
@click.option("--no-dupe-check", is_flag=True, help="Skip duplicate check(s).")
@click.option("--verbose", is_flag=True, help="Show debug messages.")
@click.version_option()
def emmet(spec_or_dbfile, run, issue, sbatch, ntries, bb, no_dupe_check, verbose):
    """Command line interface for emmet"""
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger("github3").setLevel(logging.WARNING)
    ctx = click.get_current_context()
    ctx.ensure_object(dict)

    if not sbatch and bb:
        raise EmmetCliError("Burst buffer only available in SBatch mode (--sbatch).")

    if spec_or_dbfile:
        gateway = StorageGateway.from_db_file(spec_or_dbfile)
        ctx.obj["GATEWAY"] = gateway

    if run:
        if not issue:
            raise EmmetCliError("Need issue number via --issue!")

        ctx.obj["LOG_STREAM"] = StringIO()
        memory_handler = logging.StreamHandler(ctx.obj["LOG_STREAM"])
        formatter = logging.Formatter(
            "%(asctime)s %(name)-12s %(levelname)-8s %(message)s"
        )
        memory_handler.setFormatter(formatter)
        logger.addHandler(memory_handler)

        CREDENTIALS = os.path.join(os.path.expanduser("~"), ".emmet_credentials")
        if not os.path.exists(CREDENTIALS):
            from github3 import authorize  # TODO not supported anymore

            user = click.prompt("GitHub Username")
            password = click.prompt("GitHub Password", hide_input=True)
            auth = authorize(
                user,
                password,
                ["user", "repo", "gist"],
                "emmet CLI",
                two_factor_callback=opt_prompt,
            )
            with open(CREDENTIALS, "w") as fd:
                fd.write(auth.token)

        with open(CREDENTIALS, "r") as fd:
            token = fd.readline().strip()
            ctx.obj["GH"] = gh = GitHub(session=GitHubSession(default_read_timeout=30))
            gh.login(token=token)
    else:
        click.secho("DRY RUN! Add --run flag to execute changes.", fg="green")


def safe_entry_point():
    try:
        emmet()
    except EmmetCliError as e:
        click.secho(str(e), fg="red")
    except Exception as e:
        logger.info(e, exc_info=True)


emmet.add_command(admin)
emmet.add_command(calc)
emmet.add_command(tasks)
