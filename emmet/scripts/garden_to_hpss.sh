#!/bin/bash

[[ ! -d $1/archives ]] && mkdir -v $1/archives

for block_dir in `find $1 -maxdepth 1 -type d -name "block_*"`; do
  echo $block_dir
  subdir=`basename $block_dir`
  if [ ! -e $1/archives/${subdir}.tar.gz ]; then
    tar -czvf $1/archives/${subdir}.tar.gz -C $1 $subdir
  fi
  hsi -l matcomp cput $1/archives/${subdir}.tar.gz : garden/${subdir}.tar.gz
  flag=$?
  [[ $flag -ne 0 ]] && echo "not removing ${subdir}.tar.gz (flag=$flag)" && continue
  rm -v $1/archives/${subdir}.tar.gz
done
