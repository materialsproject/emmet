# Emmet Command Line Interface
```
Usage: emmet [OPTIONS] COMMAND [ARGS]...

  Command line interface for Emmet

Options:
  --verbose  Show debug messages.
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  submit  Commands for managing an MP data submission.
```
## submit
```
Usage: emmet submit [OPTIONS] COMMAND [ARGS]...

  Commands for managing an MP data submission.

Options:
  --help  Show this message and exit.

Commands:
  add-to       Adds more files to the submission.
  create       Creates a new MP data submission.
  push         Pushes the latest version of an MP data submission.
  remove-from  Removes files from the submission.
  validate     Locally validates the latest version of an MP data...
```
### create
```
Usage: emmet submit create [OPTIONS] [PATHS]...

  Creates a new MP data submission.

  This only creates metadata about the submission. The submission will
  include all the files located in the provided files and directories paths.
  The output will contain the metadata filename path. That path will be used
  for all other actions related to this submission.

Options:
  --help  Show this message and exit.
```
### add-to
```
Usage: emmet submit add-to [OPTIONS] SUBMISSION [ADDITIONAL_PATHS]...

  Adds more files to the submission.

  This only updates the metadata about the submission.

Options:
  --help  Show this message and exit.
```
### remove-from
```
Usage: emmet submit remove-from [OPTIONS] SUBMISSION [ADDITIONAL_PATHS]...

  Removes files from the submission.

  This only updates the metadata about the submission.

Options:
  --help  Show this message and exit.
```
### validate
```
Usage: emmet submit validate [OPTIONS] SUBMISSION

  Locally validates the latest version of an MP data submission.

  The metadata submission filename path is a required argument.

Options:
  --help  Show this message and exit.
```
### push
```
Usage: emmet submit push [OPTIONS] SUBMISSION

  Pushes the latest version of an MP data submission.

  The metadata submission filename path is a required argument.

  If the files for this submission have not changed since the most recent push
  return with an error message. If the files for this submission do not pass
  local validation return with an error message.

Options:
  --help  Show this message and exit.
```

#### Remote upload configuration

`submit push` authenticates to the Materials Project submission service with
the `EMMET_API_TOKEN` environment variable. It uses
`https://api.materialsproject.org` by default; set `EMMET_API_URL` to target a
development service. Tokens and presigned URLs are never written to submission
metadata or logs. Active upload sessions are cached in the protected CLI state
directory so interrupted pushes can resume.

For each added or changed calculation, the CLI creates a complete RawArchive
HDF5 object. A JSON snapshot manifest references current calculation archives
and records removed files and calculations. The service contract is:

1. `POST /submissions/{id}/upload-sessions` prepares or refreshes an
   idempotent session and returns presigned object URLs.
2. The CLI uploads each archive and manifest with `PUT`.
3. `POST /submissions/{id}/upload-sessions/{session_id}/complete` confirms the
   uploaded object identifiers and checksums.

Local submission history advances only after the service confirms completion.
