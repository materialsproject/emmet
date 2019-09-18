#!/bin/bash

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 DIRECTORY FILTER"
  exit 1
fi

indir=$1
filter=$2
cd $indir && pwd

for block in $(find . -maxdepth 1 -type d -name "$filter" -exec basename {} \;); do
  echo $block
  [[ ! -d $block ]] && echo $block does not exist && exit
  find $block -type d -empty -print -delete
  [[ ! -d $block ]] && echo $block only contained empty directories && exit

  parallel -0m 'chmod -v g+rw {}' :::: <(find $block -not -perm -660 -print0)
  [[ $? -ne 0 ]] && echo 'error in chmod' && exit
  find $block -type f -not -name "*.gz" -exec pigz -9v {} \;
  [[ $? -ne 0 ]] && echo "error in pigz" && exit

  hsi -q -l matcomp ls -1 garden/${block}.tar
  if [ $? -ne 0 ]; then
    echo "upload new archive for ${block}"
    htar -M 5000000 -cvf garden/${block}.tar ${block}
    [[ $? -ne 0 ]] && echo "error in htar -c" && exit
  else
    echo "update existing archive for ${block}"
    htar -vtf garden/${block}.tar | awk '{ print $7 }' | sort -u > ${block}.tar.idx
    [[ $? -ne 0 ]] && echo "error in htar -t" && exit
    find $block -type f | sort -u > ${block}.idx

    # TODO check remote and local file sizes and keep larger file when extracting
    comm -13 ${block}.tar.idx ${block}.idx > ${block}.missing
    if [ -s ${block}.missing ]; then
      nfiles=$(wc -l ${block}.missing | awk '{ print $1 }')
      echo need syncing of $nfiles files
      htar -xvf garden/${block}.tar # TODO only extract what's not available locally (avoid overriding)
      [[ $? -ne 0 ]] && echo "error in htar -x" && exit
      # TODO make & keep timestamped backups
      hsi -q -l matcomp mv garden/${block}.tar garden/${block}.tar.bkp
      hsi -q -l matcomp mv garden/${block}.tar.idx garden/${block}.tar.idx.bkp
      htar -M 5000000 -cvf garden/${block}.tar ${block}
      [[ $? -ne 0 ]] && echo "error in htar -c" && exit
    else
      echo all files already in HTAR archive
    fi
    rm -v ${block}.tar.idx ${block}.idx ${block}.missing
  fi

  rm -rv ${block}
done
