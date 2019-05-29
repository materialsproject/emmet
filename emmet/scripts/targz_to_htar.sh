#!/bin/bash

# NOTE make sure matcomp is first entry in ~/.netrc!
indir=$1
year=$2
garden=garden_${year}.txt
cd $indir && pwd
hsi -P -l matcomp ls -1 "garden/block_${year}*.tar.gz" > $garden

while read block_tar_gz; do
  block=`basename ${block_tar_gz%%.tar.gz}`
  echo $block
  hsi -q -l matcomp cget garden/${block}.tar.gz
  [[ $? -ne 0 ]] && echo 'error in hsi cget' && exit
  tar -I pigz --skip-old-files -xvf ${block}.tar.gz
  [[ $? -ne 0 ]] && echo 'error in tar -x' && exit
  [[ -d garden_pauling_files/$block ]] && mv -vi garden_pauling_files/$block .
  [[ -d garden_cori/$block ]] && mv -vi garden_cori/$block .
  [[ -d garden_JulAug2018/$block ]] && mv -vi garden_JulAug2018/$block .
  [[ -d garden_Jul2018/$block ]] && mv -vi garden_Jul2018/$block .
  [[ -d garden_Aug14-16_2018/$block ]] && mv -vi garden_Aug14-16_2018/$block .
  [[ -d garden_Aug2018/$block ]] && mv -vi garden_Aug2018/$block .
  parallel -0m 'chmod -v g+rw {}' :::: <(find $block -not -perm -660 -print0)
  [[ $? -ne 0 ]] && echo 'error in chmod' && exit
  find ${block} -type f -not -name "*.gz" -exec pigz -9v {} \;
  [[ $? -ne 0 ]] && echo "error in pigz" && exit
  htar -M 5000000 -cvf garden/${block}.tar ${block}
  [[ $? -ne 0 ]] && echo 'error in htar -c' && exit
  hsi -q -l matcomp rm garden/${block}.tar.gz
  [[ $? -ne 0 ]] && echo 'error in htar rm' && exit
  rm -rv ${block}
  rm -v ${block}.tar.gz
done < $garden


