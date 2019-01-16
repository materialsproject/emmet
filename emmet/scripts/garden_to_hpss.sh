#!/bin/bash

[[ ! -d $1/archives ]] && mkdir -v $1/archives

for block_dir in `find $1 -maxdepth 1 -type d -name "block_*"`; do
  echo $block_dir
  subdir=`basename $block_dir`
  if [ ! -e $1/archives/${subdir}.tar.gz ]; then
    tar -czvf $1/archives/${subdir}.tar.gz -C $1 $subdir
    flag=$?
    if [ $flag -ne 0 ]; then
      echo "error with ${subdir}.tar.gz (flag=$flag)"
      rm -v $1/archives/${subdir}.tar.gz
      continue
    fi
  fi
  hsi -l matcomp cput $1/archives/${subdir}.tar.gz : garden/${subdir}.tar.gz
  flag=$?
  if [ $flag -ne 0 ]; then
    echo "error with hsi transfer for ${subdir}.tar.gz (flag=$flag)"
    exit
  fi
  rm -v $1/archives/${subdir}.tar.gz
  rm -rfv $block_dir
done
