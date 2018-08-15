#!/bin/bash

for block_dir in `find $1 -maxdepth 1 -type d -name "block_*"`; do
  echo $block_dir
  subdir=`basename $block_dir`
  if [ ! -e ${subdir}.tar.gz ]; then
    tar -czvf ${subdir}.tar.gz ${block_dir}
  fi
  hsi cput ${subdir}.tar.gz : garden/${subdir}.tar.gz
  [[ $? -ne 0 ]] && echo "not removing ${block_dir}" && continue
  rm -rv $block_dir && rm -v ${subdir}.tar.gz
done
