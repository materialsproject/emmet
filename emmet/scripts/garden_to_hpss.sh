#!/bin/bash

cd $1 && pwd

for block_dir in `find $1 -maxdepth 1 -type d -name "block_*"`; do
  echo $block_dir
  parallel -0m 'chmod -v g+rw {}' :::: <(find $block_dir -not -perm -660 -print0)
  [[ $? -ne 0 ]] && echo 'error in chmod' && exit
  find $block_dir -type f -not -name "*.gz" -exec pigz -9v {} \;
  [[ $? -ne 0 ]] && echo "error in pigz" && exit
  block=`basename $block_dir`
  htar -M 5000000 -cvf garden/${block}.tar $block
  [[ $? -ne 0 ]] && echo "error with htar" && exit
  rm -rfv $block_dir
done
