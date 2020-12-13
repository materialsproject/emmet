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

### tasks
```
Usage: emmet tasks -d DIRECTORY [OPTIONS]

Options:
    upload-to-nomad
    clear-uploaded
    upload-latest
    compress
    upload
    restore
```

#### tasks/upload-to-nomad
```
Description:
Upload launchers to NOMAD

Usage: emmet tasks -d DIRECTORY upload-to-nomad [OPTIONS]

Options
    --nomad-configfile  nomad user name and password json file path. Should be an absolute path
    -n/--num    maximum of launchers to upload. If n<0 upload maximum allowed by NOMAD (32*10 GB). Otherwise upload n launchers   
    --mongo-configfile  Absolute path of where the mongogrant.json is stored. Default: ~/.mongogrant.json
```

#### tasks/clear-uploaded
```
Description:
Clear launchers that have been uploaded to both GDrive and NOMAD. 

Usage: emmet tasks -d DIRECTORY clear-uploaded

Options:
    --mongo-configfile  Absolute path of where the mongogrant.json is stored. Default: ~/.mongogrant.json
```

#### tasks/upload-latest
```
Description:
Upload launchers to Gdrive in the order of latest materials. 

Usage: emmet tasks -d $SCRATCH/projects upload-latest -n 1

Options:
    --mongo-configfile  Absolute path of where the mongogrant.json is stored. Default: ~/.mongogrant.json
    -n/--num-materials  maximum number of materials to find the tasks/launchers and to upload
```

#### tasks/compress
```
Description:
Compress all directories in the input-dir, output them to output-dir using nproc processes. 

Usage: emmet tasks -d $SCRATCH/projects compress -l raw -o compressed --nproc 1

Options:
    -l/iiinput-dir  Directory of blocks to compress, relative to ('directory') ex: raw
    -o/--output-dir Directory of blocks to output the compressed blocks, relative to ('directory') ex: compressed
    --nproc Number of processes for parallel parsing
```

#### tasks/upload
```
Description:
upload all content in input-dir to GDrive

Usage:  emmet tasks -d $SCRATCH/projects -l compressed

Options:
    -l/--input-dir  Directory of blocks to upload to GDrive, relative to ('directory') ex: compressed
```

#### tasks/restore
```
Description:
Restore launchers specified in inputfile using file-filter from HPSS

Usage: 
emmet tasks -d $SCRATCH/projects -l emmet_input_file.txt -f *

Options:
    -l/--inputfile  Text file with list of launchers to restore (relative to `directory`)
    -f/--file-filter    Set the file filter(s) to match files against in each launcher.
```
