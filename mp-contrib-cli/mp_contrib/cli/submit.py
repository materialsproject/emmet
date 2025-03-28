import logging
import click
from mp_contrib.cli.utils import MPContribCliError

logger = logging.getLogger("mp_contrib_cli")

@click.group()
@click.pass_context
def submit(ctx):
    """Commands for managing an MP data submission."""
    pass

@submit.command()
@click.argument('paths', nargs=-1, type=click.Path(exists=True))
@click.pass_context
def create(ctx, paths):
    """Creates a new MP data submission.

    This only creates metadata about the submission. The submission will 
    include all the files located in the provided files and directories paths.
    The output will contain the metadata filename path. That path will be
    used for all other actions related to this submission."""

    if not paths:
        raise MPContribCliError("Must provide at least one file or directory path to include in submission")

    raise MPContribCliError("Have not implemented this yet")
    # should we check if any of this data already exists in MP (how?)
    # submission id will be a UUID

@submit.command()
@click.argument('submission', nargs=1, type=click.Path(exists=True, dir_okay=False))
@click.argument('additional_paths', nargs=-1, type=click.Path(exists=True))
@click.pass_context
def add_to(ctx, submission, additional_paths):
    """Adds more files to the submission.
    
    This only updates the metadata about the submission."""

    if not additional_paths:
        raise MPContribCliError("Must provide at least one file or directory path to add to the submission")

    raise MPContribCliError("Have not implemented this yet")

@submit.command()
@click.argument('submission', nargs=1, type=click.Path(exists=True, dir_okay=False))
@click.argument('additional_paths', nargs=-1, type=click.Path(exists=True))
@click.pass_context
def remove_from(ctx, submission, additional_paths):
    """Removes files from the submission.
    
    This only updates the metadata about the submission."""

    if not additional_paths:
        raise MPContribCliError("Must provide at least one file or directory path to remove from the submission")

    raise MPContribCliError("Have not implemented this yet")

@submit.command()
@click.argument('submission', nargs=1, type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def validate(ctx, submission):
    """Locally validates the latest version of an MP data submission. 
    
    The metadata submission filename path is a required argument. 
    
    """
    # perform a local validation (can shortcut if based on metadata)
    raise MPContribCliError("Have not implemented this yet")

@submit.command()
@click.argument('submission', nargs=1, type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def push(ctx, submission):
    """Pushes the latest version of an MP data submission. 
    
    The metadata submission filename path is a required argument. 
    
    If the files for this submission have not changed since the most recent push
    return with an error message.
    If the files for this submission do not pass local validation return with an
    error message.
    """
    updated_file_info = get_changed_since_last_push(submission)
    logger.debug(f"Changes in files for submission since last update: {updated_file_info}")
    if not updated_file_info:
        raise MPContribCliError("Files for submission have not changed since last update. Not pushing.")

    already_contributed_file_info = get_already_contributed(updated_file_info)
    logger.debug(f"Files for submission considered to be duplicates: {already_contributed_file_info}")
    if already_contributed_file_info:
        raise MPContribCliError(f"The following are considered to be duplicates of data already in MP {already_contributed_file_info}")

    # perform local validation
    ctx.invoke(validate, submission=submission)

    do_push(submission, updated_file_info)

    logger.info(f"Successfuly update submission in {submission}")
    pass

def get_changed_since_last_push(submission):
    # check whether the files for submission have changed since last update
    #    (this can be done by checking hashes against values stored in the metadata about last push)
    # returns a dictionary of file names -> metadata
    return {"foo" : "changed"}

def get_already_contributed(updated_file_info):
    # if doing checks for data already in MP check the changed data against MP
    return {}

def do_push(path, updated_file_info):
    # push updated submission (push id will be UUID)
    #    (can later determine whether to upload all each time or just diffs)
    raise MPContribCliError("Have not implemented this yet")