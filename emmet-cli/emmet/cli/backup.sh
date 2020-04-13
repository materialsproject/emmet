#!/bin/bash -l
#SBATCH --qos=xfer
#SBATCH --time=48:00:00
#SBATCH --job-name=garden_to_hpss
#SBATCH --licenses=SCRATCH
#SBATCH --mail-user=phuck@lbl.gov
#SBATCH --mail-type=ALL
#SBATCH --output=garden_to_hpss-%j.out
#SBATCH --error=garden_to_hpss-%j.error

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 DIRECTORY FILTER"
  exit 1
fi

indir=$1
filter=$2
stage_dir=$indir/tmp

cd $indir && pwd
[[ ! -d $stage_dir ]] && mkdir -pv $stage_dir

for block in $(find . -maxdepth 1 -type d -group matgen -name "$filter" -exec basename {} \;); do
  echo $block


  hsi -q -l matcomp ls -1 garden/${block}.tar
  if [ $? -ne 0 ]; then
    echo "upload new archive for ${block}"
    htar -M 5000000 -cvf garden/${block}.tar ${block}
    [[ $? -ne 0 ]] && echo "error in htar -c" && exit
  #else
  #  echo "update existing archive for ${block}"
  #  htar -vtf garden/${block}.tar | awk '{ print $7 }' | sort -u > ${block}.tar.idx
  #  [[ $? -ne 0 ]] && echo "error in htar -t" && exit
  #  find $block -type f | sort -u > ${block}.idx

  #  # TODO check remote and local file sizes and keep larger file when extracting
  #  comm -13 ${block}.tar.idx ${block}.idx > ${block}.missing
  #  if [ -s ${block}.missing ]; then
  #    nfiles=$(wc -l ${block}.missing | awk '{ print $1 }')
  #    echo need syncing of $nfiles files
  #    htar -xvf garden/${block}.tar # TODO only extract what's not available locally (avoid overriding)
  #    [[ $? -ne 0 ]] && echo "error in htar -x" && exit
  #    # TODO make & keep timestamped backups
  #    hsi -q -l matcomp mv garden/${block}.tar garden/${block}.tar.bkp
  #    hsi -q -l matcomp mv garden/${block}.tar.idx garden/${block}.tar.idx.bkp
  #    htar -M 5000000 -cvf garden/${block}.tar ${block}
  #    [[ $? -ne 0 ]] && echo "error in htar -c" && exit
  #  else
  #    echo all files already in HTAR archive
  #  fi
  #  rm -v ${block}.tar.idx ${block}.idx ${block}.missing
  fi

  # TODO get list of launchers for current block from $indir
  launchers=`grep $block $all_launchers`
  nlaunchers=`echo $launchers | wc -w`
  list=""
  for l in $launchers; do
    [[ ! -e $stage_dir/$l ]] && list="$list $l/std_err.txt.gz $l/FW_job.error.gz"
    length=`echo $list | wc -w`
    [[ $length -gt 500 ]] && cd $stage_dir && htar -xvf garden/${block}.tar $list && list="" && cd -
  done
  [[ ! -z "$list" ]] && cd $stage_dir && htar -xvf garden/${block}.tar $list && cd -
  nrestored=`ls -1 $stage_dir/$block | wc -l`
  echo $nlaunchers $nrestored
  [[ ! $nlaunchers -eq $nrestored ]] && echo 'missing launchers!' && exit;
  rm -rv $indir/$block && rm -rv $indir/$stage_dir/$block

  # TODO get full list of files for current block
  files=`grep "^$dir" $input`

  echo $files | tr ' ' '\n' | sort -u > ${dir}.files
  wc -l ${dir}.files
  rclone lsf -R --files-only mp-drive:calculations/garden/$dir | sed "s:^:$dir/:g" | sed 's:.tar.gz::g' | sort -u > ${dir}.rclone_lsf
  wc -l ${dir}.rclone_lsf

  missing_paths=${dir}.paths
  [[ -e $missing_paths ]] && rm -v $missing_paths
  for f in $(comm --check-order -23 ${dir}.files ${dir}.rclone_lsf); do # launch dirs missing in mp-drive
    launch_dir_tar="${stage_dir}/${f}.tar.gz"
    if [[ ! -f $launch_dir_tar || ! -s $launch_dir_tar ]]; then
      echo $f >> $missing_paths
    elif [ -d $f ]; then
      rm -rv $f
    fi
  done

  for f in $(comm --check-order -12 ${dir}.files ${dir}.rclone_lsf | tr '\n' ' '); do # already cloned launch dirs -> cleanup
    launch_dir_tar="${stage_dir}/${f}.tar.gz"
    [[ -d $f ]] && rm -rv $f
    [[ -e $launch_dir_tar ]] && rm -v $launch_dir_tar
  done
  rm -v ${dir}.files ${dir}.rclone_lsf

  [[ ! -e $missing_paths ]] && echo nothing missing on GDrive!? && continue
  wc -l $missing_paths

  htar -xvf garden/${dir}.tar `cat $missing_paths | tr '\n' ' '`
  ls -ltrhd ${dir}
  [[ $? -ne 0 ]] && echo missing paths not found in HPSS!? && continue

  for f in `cat $missing_paths`; do
    [[ ! -e $f ]] && echo $f not found in HPSS!? && continue
    launch_dir_tar="${stage_dir}/${f}.tar.gz"
    echo $launch_dir_tar ...
    mkdir -p `dirname $launch_dir_tar`
    if tar --use-compress-program="pigz -9rv" -cf $launch_dir_tar -C `dirname $f` `basename $f`; then
      ls -ltrh $launch_dir_tar
    else
      echo 'problem with launch dir tar!'
      rm -v $launch_dir_tar
      exit
    fi
    [[ -d $f ]] && rm -rv $f
  done
  rm -v $missing_paths

  rclone -v copy $stage_dir/$dir mp-drive:calculations/garden/$dir
  find $dir -type d -empty -print -delete

done

echo DONE
