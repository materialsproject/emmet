# MP Contrib Command Line Interface
```
Usage: mp-contrib [OPTIONS] COMMAND [ARGS]...

  Command line interface for MP contributions

Options:
  --verbose  Show debug messages.
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  submit  Commands for managing an MP data submission.
```
## submit
```
Usage: mp-contrib submit [OPTIONS] COMMAND [ARGS]...

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
Usage: mp-contrib submit create [OPTIONS] [PATHS]...

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
Usage: mp-contrib submit add-to [OPTIONS] SUBMISSION [ADDITIONAL_PATHS]...

  Adds more files to the submission.

  This only updates the metadata about the submission.

Options:
  --help  Show this message and exit.
```
### remove-from
```
Usage: mp-contrib submit remove-from [OPTIONS] SUBMISSION
                                     [ADDITIONAL_PATHS]...

  Removes files from the submission.

  This only updates the metadata about the submission.

Options:
  --help  Show this message and exit.
```
### validate
```
Usage: mp-contrib submit validate [OPTIONS] SUBMISSION

  Locally validates the latest version of an MP data submission.

  The metadata submission filename path is a required argument.

Options:
  --help  Show this message and exit.
```
### push
```
Usage: mp-contrib submit push [OPTIONS] SUBMISSION

  Pushes the latest version of an MP data submission.

  The metadata submission filename path is a required argument.

  If the files for this submission have not changed since the most recent push
  return with an error message. If the files for this submission do not pass
  local validation return with an error message.

Options:
  --help  Show this message and exit.
```
