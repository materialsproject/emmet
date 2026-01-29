import contextlib
import io
import logging
import os
from datetime import datetime
from functools import update_wrapper
from enum import Enum

import click
from slurmpy import Slurm
from github3.gists import ShortGist

from emmet.cli.legacy import SETTINGS
from emmet.cli.legacy.utils import EmmetCliError, ReturnCodes, reconstruct_command

logger = logging.getLogger("emmet")
COMMENT_TEMPLATE = """
<details><summary><b>{}</b> {}.</summary><p>

```
{}
```

[Logs]({})

</p></details>
"""
GIST_COMMENT_TEMPLATE = "**[Gist]({}) created** to collect command logs for this issue."
GIST_RAW_URL = "https://gist.githubusercontent.com"


def track(func):
    """decorator to track command in GH issue / gists"""

    def wrapper(*args, **kwargs):
        ret = func(*args, **kwargs)
        ctx = click.get_current_context()
        if not isinstance(ret, Enum):
            raise EmmetCliError(f"Tracking `{ctx.command_path}` requires Enum!")

        if ctx.grand_parent.params["run"]:
            logger.info(ret.value)
            gh = ctx.grand_parent.obj["GH"]
            user = gh.me().login
            issue_number = ctx.grand_parent.params["issue"]
            issue = gh.issue(
                SETTINGS.tracker["org"], SETTINGS.tracker["repo"], issue_number
            )

            # create or retrieve gist for log files
            gist_name = f"{SETTINGS.tracker['repo']}-issue{issue_number}.md"
            emmet_dir = os.path.join(os.path.expanduser("~"), ".emmet")
            if not os.path.exists(emmet_dir):
                os.mkdir(emmet_dir)
                logger.debug(f"{emmet_dir} created")

            gist_id_fn = os.path.join(emmet_dir, gist_name)
            gist = None

            if os.path.exists(gist_id_fn):
                with open(gist_id_fn, "r") as fd:
                    gist_id = fd.readline().strip()
                    # NOTE failed with KeyError 'total': gist = gh.gist(gist_id)
                    url = gh._build_url("gists", str(gist_id))
                    resp = gh._get(url)
                    json = gh._json(resp, 200)
                    gist = gh._instance_or_null(ShortGist, json)
            else:
                description = f"Logs for {SETTINGS.tracker['repo']}#{issue_number}"
                files = {gist_name: {"content": issue.html_url}}
                gist = gh.create_gist(description, files, public=False)
                with open(gist_id_fn, "w") as fd:
                    fd.write(gist.id)

                txt = GIST_COMMENT_TEMPLATE.format(gist.html_url)
                comment = issue.create_comment(txt)
                logger.info(f"Gist Comment: {comment.html_url}")

            # update gist with logs for new command
            logger.debug(f"Log Gist: {gist.html_url}")
            now = str(datetime.now()).replace(" ", "-")
            filename = ctx.command_path.replace(" ", "-") + f"_{now}"
            logs = ctx.grand_parent.obj["LOG_STREAM"]
            gist.edit(files={filename: {"content": logs.getvalue()}})

            if not ctx.grand_parent.params["sbatch"]:
                # add comment for new command
                command = reconstruct_command()
                raw_url = f"{GIST_RAW_URL}/{user}/{gist.id}/raw/{filename}"
                txt = COMMENT_TEMPLATE.format(
                    ctx.command_path, ret.value, command, raw_url
                )
                comment = issue.create_comment(txt)
                logger.info(comment.html_url)

        return ret

    return update_wrapper(wrapper, func)


def sbatch(func):
    """decorator to enable SLURM mode on command"""

    @track
    def wrapper(*args, **kwargs):
        ctx = click.get_current_context()
        ctx.grand_parent = ctx.parent.parent
        if not ctx.grand_parent.params["sbatch"]:
            return ctx.invoke(func, *args, **kwargs)

        run = ctx.grand_parent.params["run"]
        ntries = ctx.grand_parent.params["ntries"]
        if run:
            click.secho(
                f"SBATCH MODE! Submitting to SLURM queue with {ntries} tries.",
                fg="green",
            )

        directory = ctx.parent.params["directory"]
        if not directory:
            raise EmmetCliError(f"{ctx.parent.command_path} needs --directory option!")

        track_dir = os.path.join(directory, ".emmet")
        if run and not os.path.exists(track_dir):
            os.mkdir(track_dir)
            logger.debug(f"{track_dir} created")

        bb = ctx.grand_parent.params["bb"]
        if bb:
            subdir = directory.rsplit(os.sep, 1)[1]
            stage_in = f"#DW stage_in source={directory} "
            stage_in += f"destination=$DW_JOB_STRIPED/{subdir} type=directory"
            script = [
                "#DW jobdw capacity=10TB access_mode=striped type=scratch",
                stage_in,
                "srun hostname",
                "",
            ]

            command = "\n".join(script)
            slurm_kwargs = {
                "qos": "premium",
                "nodes": 1,
                "tasks-per-node": 1,
                "constraint": "haswell",
                "time": "48:00:00",
            }
        else:
            slurm_kwargs = {
                "qos": "xfer",
                "time": "48:00:00",
                "licenses": "SCRATCH",
                "mem": "12GB",
                "mail-user": "tsm@lbl.gov"
                "mail-type": "ALL"
            }
            command = ""

        s = Slurm(
            ctx.command_path.replace(" ", "-"),
            slurm_kwargs=slurm_kwargs,
            date_in_name=False,
            scripts_dir=track_dir,
            log_dir=track_dir,
            bash_strict=False,
        )

        command += reconstruct_command(sbatch=True)
        slurmpy_stderr = io.StringIO()
        with contextlib.redirect_stderr(slurmpy_stderr):
            s.run(command, _cmd="sbatch" if run else "cat", tries=ntries)

        ret = slurmpy_stderr.getvalue()[2:-2].encode("utf-8").decode("unicode_escape")

        if run:
            slurm_id = ret.split()[-1]
            ReturnCodesDynamic = Enum(
                "ReturnCodesDynamic", {"SUBMITTED": f"SLURM {slurm_id}"}
            )
            return ReturnCodesDynamic.SUBMITTED

        logger.info(ret)
        return ReturnCodes.SUCCESS

    return update_wrapper(wrapper, func)
