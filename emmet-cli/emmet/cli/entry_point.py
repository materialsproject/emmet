import os
import logging
import click

from log4mongo.handlers import BufferedMongoHandler
from github3 import authorize, login
from io import StringIO

from emmet.cli.admin import admin
from emmet.cli.tasks import tasks
from emmet.cli.calc import calc
from emmet.cli.utils import calcdb_from_mgrant, ensure_indexes
from emmet.cli.utils import EmmetCliError


logger = logging.getLogger("")
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


def opt_prompt():
    return click.prompt("GitHub OPT", hide_input=True)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("--spec", metavar="HOST/DB", help="MongoGrant spec for user DB.")
@click.option("--run", is_flag=True, help="Run DB/filesystem write operations.")
@click.option("--issue", type=int, help="Production tracker issue (required if --run).")
@click.option("--sbatch", is_flag=True, help="Switch to sbatch mode.")
@click.option("--no-dupe-check", is_flag=True, help="Skip duplicate check(s).")
@click.option("--verbose", is_flag=True, help="Show debug messages.")
@click.version_option()
def emmet(spec, run, issue, sbatch, no_dupe_check, verbose):
    """Command line interface for emmet"""
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    ctx = click.get_current_context()
    ctx.ensure_object(dict)

    if spec:
        client = calcdb_from_mgrant(spec)
        ctx.obj["CLIENT"] = client
        ctx.obj["MONGO_HANDLER"] = BufferedMongoHandler(
            host=client.host,
            port=client.port,
            database_name=client.db_name,
            username=client.user,
            password=client.password,
            level=logging.WARNING,
            authentication_db=client.db_name,
            collection="emmet_logs",
            buffer_periodical_flush_timing=False,  # flush manually
        )
        logger.addHandler(ctx.obj["MONGO_HANDLER"])
        coll = ctx.obj["MONGO_HANDLER"].collection
        created = ensure_indexes(SETTINGS.log_fields, [coll])
        if created:
            indexes = ", ".join(created[coll.full_name])
            logger.debug(
                f"Created the following index(es) on {coll.full_name}:\n{indexes}"
            )

    if run:
        if not issue:
            org, repo = SETTINGS.tracker["org"], SETTINGS.tracker["repo"]
            url = f"https://github.com/{org}/{repo}/issues"
            raise EmmetCliError(f"Link to issue number at {url} via --issue!")

        ctx.obj["LOG_STREAM"] = StringIO()
        memory_handler = logging.StreamHandler(ctx.obj["LOG_STREAM"])
        formatter = logging.Formatter(
            "%(asctime)s %(name)-12s %(levelname)-8s %(message)s"
        )
        memory_handler.setFormatter(formatter)
        logger.addHandler(memory_handler)

        CREDENTIALS = os.path.join(os.path.expanduser("~"), ".emmet_credentials")
        if not os.path.exists(CREDENTIALS):
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
            ctx.obj["GH"] = login(token=token)
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
