#!/bin/bash

# NOTE make sure matcomp is first entry in ~/.netrc!
cd $1 && pwd
hsi -P -l matcomp ls -1 "garden/*.tar.gz" > garden.txt

while read block_tar_gz; do
  block=`basename ${block_tar_gz%%.tar.gz}`
  echo $block
  hsi -q -l matcomp cget garden/${block}.tar.gz
  [[ $? -ne 0 ]] && echo 'error in hsi cget' && exit
  tar -I pigz --skip-old-files -xvf ${block}.tar.gz
  [[ $? -ne 0 ]] && echo 'error in tar -x' && exit
  find $block -not -perm -660 -exec chmod -v g+rw {} \;
  [[ $? -ne 0 ]] && echo 'error in chmod' && exit
  find ${block} -type f -not -name "*.gz" -exec pigz -9v {} \;
  [[ $? -ne 0 ]] && echo "error in pigz" && exit
  htar -M 5000000 -cvf garden/${block}.tar ${block}
  [[ $? -ne 0 ]] && echo 'error in htar -c' && exit
  hsi -q -l matcomp rm garden/${block}.tar.gz
  [[ $? -ne 0 ]] && echo 'error in htar rm' && exit
  rm -rv ${block}
  rm -v ${block}.tar.gz
done < garden.txt


