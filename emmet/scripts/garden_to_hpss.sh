#!/bin/bash

cd $1 && pwd

for block_dir in `find $1 -maxdepth 1 -type d -name "block_*"`; do
  echo $block_dir
  chmod -Rv ug+rw $block_dir
  [[ $? -ne 0 ]] && echo 'error in chmod' && exit
  find $block_dir -type f -not -name "*.gz" -exec pigz -9v {} \;
  [[ $? -ne 0 ]] && echo "error in pigz" && exit
  block=`basename $block_dir`
  htar -cvf garden/${block}.tar $block
  flag=$?
  if [ $flag -ne 0 ]; then
    echo "error with htar (flag=$flag)"
    exit
  fi
  #rm -rfv $block_dir
  break
done
