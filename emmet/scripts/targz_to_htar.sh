#!/bin/bash

# NOTE make sure matcomp is first entry in ~/.netrc!
[[ ! -e garden.txt ]] && hsi -P -l matcomp ls -1 "garden/*.tar.gz" > garden.txt

while read block_tar_gz; do
  block=`basename ${block_tar_gz%%.tar.gz}`
  echo $block
  if [ ! -e ${block}.tar.gz ]; then
    hsi -q -l matcomp get garden/${block}.tar.gz
    [[ $? -ne 0 ]] && echo 'error in hsi get' && exit
  fi
  if [ ! -d ${block} ]; then
    tar -xvzf ${block}.tar.gz
    [[ $? -ne 0 ]] && echo 'error in tar -x' && exit
  fi
  chmod -Rv ug+rw ${block}
  [[ $? -ne 0 ]] && echo 'error in chmod' && exit
  find ${block} -type f -not -name "*.gz" -exec pigz -9v {} \;
  [[ $? -ne 0 ]] && echo "error in pigz" && exit
  htar -cvf garden/${block}.tar ${block}
  [[ $? -ne 0 ]] && echo 'error in htar -c' && exit
  hsi -q -l matcomp rm garden/${block}.tar.gz
  [[ $? -ne 0 ]] && echo 'error in htar rm' && exit
  rm -rv ${block}
  rm -v ${block}.tar.gz
  break # TODO remove
done < garden.txt


