import os
import io
import click
import logging
import contextlib

from datetime import datetime
from functools import update_wrapper
from slurmpy import Slurm

from emmet.cli.config import tracker
from emmet.cli.utils import reconstruct_command, EmmetCliError, ReturnCodes

logger = logging.getLogger("emmet")
COMMENT_TEMPLATE = """
<details><summary><b>{}</b> {}.</summary><p>

```
{}
```

[Logs]({})

</p></details>
"""
GIST_COMMENT_TEMPLATE = "**[Gist]({}) created** to collect command logs for this issue. Download latest set of log files [here]({})."
GIST_RAW_URL = "https://gist.githubusercontent.com"


def track(func):
    """decorator to track command in GH issue / gists"""

    def wrapper(*args, **kwargs):
        ret = func(*args, **kwargs)
        ctx = click.get_current_context()
        if not isinstance(ret, ReturnCodes):
            raise EmmetCliError(f"Tracking `{ctx.command_path}` requires ReturnCode!")

        if ctx.grand_parent.params["run"]:
            logger.info(ret.value)
            gh = ctx.grand_parent.obj["GH"]
            user = gh.me().login
            issue_number = ctx.grand_parent.params["issue"]
            issue = gh.issue(tracker["org"], tracker["repo"], issue_number)

            # gists iterator/resource based on latest etag
            ETAG = os.path.join(os.path.expanduser("~"), ".emmet_etag")
            etag = None
            if os.path.exists(ETAG):
                with open(ETAG, "r") as fd:
                    etag = fd.readline().strip()

            gists_iterator = gh.gists(etag=etag)
            if gists_iterator.etag != etag:
                with open(ETAG, "w") as fd:
                    fd.write(gists_iterator.etag)

            # create or retrieve gist for log files
            gist_name = f"#{issue_number}-{tracker['repo']}.md"
            for gist in gists_iterator:
                if gist.files and gist_name in gist.files:
                    break
            else:
                description = f"Logs for {tracker['repo']}#{issue_number}"
                files = {gist_name: {"content": issue.html_url}}
                gist = gh.create_gist(description, files, public=False)
                zip_base = gist.html_url.replace(gist.id, user + "/" + gist.id)
                txt = GIST_COMMENT_TEMPLATE.format(
                    gist.html_url, zip_base + "/archive/master.zip"
                )
                comment = issue.create_comment(txt)
                logger.info(f"Gist Comment: {comment.html_url}")

            # update gist with logs for new command
            logger.info(f"Log Gist: {gist.html_url}")
            now = str(datetime.now()).replace(" ", "-")
            filename = ctx.command_path.replace(" ", "-") + f"_{now}"
            logs = ctx.grand_parent.obj["LOG_STREAM"]
            gist.edit(files={filename: {"content": logs.getvalue()}})

            # add comment for new command
            command = reconstruct_command()
            raw_url = f"{GIST_RAW_URL}/{user}/{gist.id}/raw/{filename}"
            txt = COMMENT_TEMPLATE.format(ctx.command_path, ret.value, command, raw_url)
            comment = issue.create_comment(txt)
            logger.info(comment.html_url)

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
        if run:
            click.secho(f"SBATCH MODE! Submitting to SLURM queue.", fg="green")

        directory = ctx.parent.params.get("directory")
        if not directory:
            raise EmmetCliError(f"{ctx.parent.command_path} needs --directory option!")

        track_dir = os.path.join(directory, ".emmet")
        if run and not os.path.exists(track_dir):
            os.mkdir(track_dir)
            logger.debug(f"{track_dir} created")

        s = Slurm(
            ctx.command_path.replace(" ", "-"),
            slurm_kwargs={"qos": "xfer", "time": "48:00:00", "licenses": "SCRATCH"},
            date_in_name=False,
            scripts_dir=track_dir,
            log_dir=track_dir,
            bash_strict=False,
        )

        command = reconstruct_command(sbatch=True)
        slurmpy_stderr = io.StringIO()
        with contextlib.redirect_stderr(slurmpy_stderr):
            s.run(command, _cmd="sbatch" if run else "cat")
        ret = slurmpy_stderr.getvalue()[2:-1]
        logger.info("\n" + ret.encode("utf-8").decode("unicode_escape"))
        return ReturnCodes.SUBMITTED if run else ReturnCodes.SUCCESS

    return update_wrapper(wrapper, func)
