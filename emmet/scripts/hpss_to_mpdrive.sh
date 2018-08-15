#!/bin/bash

# $(find $dir -name 'INCAR.orig*' -printf '%h ')
dirs=`awk -F/ '{print $1}' $1 | sort -u`
hpss_missing="blocks_missing_in_hpss.txt"

stage_dir="rclone_to_mp_drive"
[[ ! -d $stage_dir ]] && mkdir $stage_dir
[[ ! -e $hpss_missing ]] && touch $hpss_missing

for dir in $dirs; do
  [[ ! -e ${dir}.tar.gz ]] && echo "skip ${dir}" && continue # TODO remove

  files=`grep "^$dir" $1`
  extract="${dir}.extract"
  grep -q "$dir" $hpss_missing
  [[ $? -eq 0 ]] && continue

  [[ -d $stage_dir/$dir ]] && rclone -v copy $stage_dir/$dir mp-drive:calculations/garden/$dir

  missing_paths="${dir}.paths"
  echo $files | tr ' ' '\n' | sort -u > ${dir}.files
  rclone lsf -R --files-only mp-drive:calculations/garden/$dir | sed "s:^:$dir/:g" | sed 's:.tar.gz::g' | sort -u > ${dir}.rclone_lsf
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

  [[ ! -e $missing_paths ]] && continue

  if [ ! -e ${dir}.tar.gz ] || [ ! -s ${dir}.tar.gz ]; then
    hsi -q "get garden/${dir}.tar.gz"
    [[ $? -ne 0 ]] && echo ${dir} >> $hpss_missing && continue
  fi
  ls -ltrh ${dir}.tar.gz

  if [ ! -e ${dir}.tar_list ] || [ ! -s ${dir}.tar_list ]; then
    echo "make ${dir}.tar_list ..."
    tar -tzvf ${dir}.tar.gz | grep ^d | grep -v -e '/relax1/' -e '/relax2/' | awk {'print $6'} 2>&1 | tee ${dir}.tar_list
  fi

  paths=`cat $missing_paths`
  for f in $paths; do
    [[ ! -d $f ]] && grep $f ${dir}.tar_list >> $extract
  done

  if [ -e $extract ] && [ -s $extract ]; then
    echo "extract" `wc -l $extract`
    tar -xvzf ${dir}.tar.gz --files-from $extract
  fi
  rm -v $extract

  for f in $paths; do
    launch_dir_tar="${stage_dir}/${f}.tar.gz"
    echo $launch_dir_tar ...
    mkdir -p `dirname $launch_dir_tar`
    tar_code=$(tar -czf $launch_dir_tar -C `dirname $f` `basename $f`)
    [[ $tar_code -ne 0 ]] && echo 'problem with launch dir tar!' && break
    ls -ltrh $launch_dir_tar
    [[ -d $f ]] && rm -r $f
  done
  rm -v $missing_paths

  rclone -v copy $stage_dir/$dir mp-drive:calculations/garden/$dir

done
