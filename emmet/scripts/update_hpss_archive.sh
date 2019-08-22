#!/bin/bash

indir=/project/projectdirs/matgen/garden/hpss_to_mpdrive/raw
cd $indir && pwd

#for block in $(find . -maxdepth 1 -type d -name "block_2011*" -exec basename {} \;); do
#for block in $(cat hpss_update_2013.txt); do
for block_targz in $(ls block_201*.tar.gz); do
  tar -I pigz --skip-old-files -xvf ${block_targz}
  [[ $? -ne 0 ]] && echo "error in tar -x" && exit
  block=${block_targz%%.tar.gz}
  echo $block
  [[ ! -d $block ]] && echo $block does not exist && exit
  find $block -type d -empty -print -delete
  [[ ! -d $block ]] && echo $block only contained empty directories && exit

  parallel -0m 'chmod -v g+rw {}' :::: <(find $block -not -perm -660 -print0)
  [[ $? -ne 0 ]] && echo 'error in chmod' && exit
  find $block -type f -not -name "*.gz" -exec pigz -9v {} \;
  [[ $? -ne 0 ]] && echo "error in pigz" && exit

  htar -vtf garden/${block}.tar | awk '{ print $7 }' | sort -u > ${block}.tar.idx
  [[ $? -ne 0 ]] && echo "error in htar -t" && exit
  find $block -type f | sort -u > ${block}.idx

  comm -13 ${block}.tar.idx ${block}.idx > ${block}.missing
  if [ -s ${block}.missing ]; then
    nfiles=$(wc -l ${block}.missing | awk '{ print $1}')
    echo need syncing of $nfiles files
    htar -xvf garden/${block}.tar
    [[ $? -ne 0 ]] && echo "error in htar -x" && exit
    hsi -q -l matcomp mv garden/${block}.tar garden/${block}.tar.bkp
    hsi -q -l matcomp mv garden/${block}.tar.idx garden/${block}.tar.idx.bkp
    htar -M 5000000 -cvf garden/${block}.tar ${block}
    [[ $? -ne 0 ]] && echo "error in htar -c" && exit
    hsi -q -l matcomp rm garden/${block}.tar*.bkp
    [[ $? -ne 0 ]] && echo 'error in htar rm' && exit
  else
    echo all files already in HTAR archive
  fi
  rm -rv ${block}
  rm -v ${block}.tar.idx ${block}.idx ${block}.missing
  rm -v ${block_targz}
done
