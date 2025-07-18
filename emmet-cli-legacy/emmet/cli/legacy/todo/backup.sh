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
