import os
import click

from datetime import datetime
from functools import update_wrapper
from slurmpy import Slurm

from emmet.cli.config import tracker
from emmet.cli.utils import reconstruct_command, EmmetCliError

logger = logging.getLogger("emmet")
COMMENT_TEMPLATE = """
<details><summary><b>{}</b> returned "{}"</summary><p>

```
{}
```

[Logs]({})

</p></details>
"""
GIST_COMMENT_TEMPLATE = """
**[Gist]({url}) created** to collect command logs for this issue. The current set of
log files can be downloaded [here]({url}/archive/master.zip).
"""


def track(func):
    """decorator to track command in GH issue / gists"""
    def wrapper(*args, **kwargs):
        ret = func(*args, **kwargs)
        ctx = click.get_current_context()
        run = ctx.grand_parent.params["run"]

        if run and ret:
            logger.info(ret)
            command = reconstruct_command()
            gh = ctx.grand_parent.obj["GH"]
            issue_number = ctx.grand_parent.params["issue"]
            issue = gh.issue(tracker["org"], tracker["repo"], issue_number)

            # gists iterator/resource based on latest etag
            ETAG = os.path.join(os.path.expanduser("~"), '.emmet_etag')
            etag = None
            if os.path.exists(ETAG):
                with open(ETAG, 'r') as fd:
                    etag = fd.readline().strip()

            gists_iterator = gh.gists(etag=etag)
            if gists_iterator.etag != etag:
                with open(ETAG, 'w') as fd:
                    fd.write(gists_iterator.etag)

            # create or retrieve gist for log files
            gist_name = f"#{issue_number}-{tracker['repo']}.md"
            for gist in gists_iterator:
                if gist.files[0].filename == gist_name:
                    break
            else:
                description = f"Logs for {tracker['repo']}#{issue_number}"
                files = {gist_name: {"content": issue.html_url}}
                gist = gh.create_gist(description, files, public=False)
                txt = GIST_COMMENT_TEMPLATE.format(url=gist.html_url)
                comment = issue.create_comment(txt)
                logger.info(f"Gist Comment: {comment.html_url}")

            logger.info(f"Log Gist: {gist.html_url}")


                # TODO update
            now = str(datetime.now()).replace(" ", "-")
            fn = ctx.command_path.replace(" ", "-") + f"_{now}"
            logs = ctx.grand_parent.obj["LOG_STREAM"]
            files = {fn: {"content": logs.getvalue()}}



            # TODO hide previous comments?
            # TODO link to raw log file
            raw_url =
            # https://gist.githubusercontent.com/tschaume/43ee0a71e74eb68d23368f6fcd56b04f/raw/ecf10823056fe07fe8f83acf9d5bb169090a9af9/emmet-hpss-prep_2020-04-14-01:51:29.944896
            txt = COMMENT_TEMPLATE.format(ctx.command_path, ret, command, raw_url)
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

        track_dir = os.path.join(directory, '.emmet')
        if run and not os.path.exists(track_dir):
            os.mkdir(track_dir)
            logger.debug(f"{track_dir} created")

        s = Slurm(
            ctx.command_path.replace(" ", "-"),
            slurm_kwargs={
                "qos": "xfer",
                "time": "48:00:00",
                "licenses": "SCRATCH"
            },
            date_in_name=False,
            scripts_dir=track_dir,
            log_dir=track_dir,
            bash_strict=False,
        )

        command = reconstruct_command(sbatch=True)
        ret = s.run(command, _cmd="sbatch" if run else "ls")
        return f"SBatch JobId: {ret}" if run else ret

    return update_wrapper(wrapper, func)
