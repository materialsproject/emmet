# Emmet Command Line Interface
```
Usage: emmet [OPTIONS] COMMAND [ARGS]...

  Command line interface for emmet

Options:
  --spec HOST/DB   MongoGrant spec for user database.  [required]
  --run            Run DB/filesystem write operations.
  --no-dupe-check  Skip duplicate check(s).
  --verbose        Show debug messages.
  --version        Show the version and exit.
  --help           Show this message and exit.

Commands:
  admin  Administrative and utility commands
  calc   Set up calculations to optimize structures using VASP
```
## admin
```
Usage: emmet admin [OPTIONS] COMMAND [ARGS]...

  Administrative and utility commands

Options:
  --help  Show this message and exit.

Commands:
  index  Create index(es) for fields of a collection
  meta   Create meta-data fields and indexes for SNL collection
  reset  Reset collections for tag(s)
```
### index
```
Usage: emmet admin index [OPTIONS] [FIELDS]... COLLECTION

  Create index(es) for fields of a collection

Options:
  --help  Show this message and exit.
```
### meta
```
Usage: emmet admin meta [OPTIONS] COLLECTION

  Create meta-data fields and indexes for SNL collection

Options:
  --help  Show this message and exit.
```
### reset
```
Usage: emmet admin reset [OPTIONS] [TAGS]...

  Reset collections for tag(s)

Options:
  --help  Show this message and exit.
```
## calc
```
Usage: emmet calc [OPTIONS] COMMAND [ARGS]...

  Set up calculations to optimize structures using VASP

Options:
  -s SPEC             Add DB(s) with SNL/task collection(s) to dupe-check.
  -m INTEGER          Maximum #structures to scan.  [default: 1000]
  --skip / --no-skip  Skip already scanned structures.  [default: True]
  --help              Show this message and exit.

Commands:
  add   Add workflows for structures with tag in SNL collection
  prep  prep structures from an archive for submission
```
### prep
```
Usage: emmet calc prep [OPTIONS] ARCHIVE

  prep structures from an archive for submission

Options:
  -a AUTHOR  Author to assign to all structures.  [default: Materials Project
             <feedback@materialsproject.org>]

  --help     Show this message and exit.
```
### add
```
Usage: emmet calc add [OPTIONS] TAG

  Add workflows for structures with tag in SNL collection

Options:
  --help  Show this message and exit.
```
