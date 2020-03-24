#!/bin/bash -l
#SBATCH --qos=xfer
#SBATCH --time=48:00:00
#SBATCH --job-name=check_remove
#SBATCH --licenses=SCRATCH
#SBATCH --mail-user=phuck@lbl.gov
#SBATCH --mail-type=ALL
#SBATCH --output=check_remove-%j.out
#SBATCH --error=check_remove-%j.error

indir=/global/cscratch1/sd/jmunro/bs_split_production/data
all_launchers=jmunro_parse_check_remove_bs_split_production.txt

blocks=`cut -d/ -f1 $all_launchers | sort -u`
echo $blocks | wc -w

[[ ! -d $indir/tmp ]] && mkdir $indir/tmp

for block in $blocks; do
  echo $block
  #hsi -q -l matcomp ls -1 garden/${block}.tar
  #if [ ! $? -eq 0 ]; then echo "$block.tar not backed up!"; continue; fi
  launchers=`grep $block $all_launchers`
  nlaunchers=`echo $launchers | wc -w`
  list=""
  for l in $launchers; do
    [[ ! -e $indir/tmp/$l ]] && list="$list $l/std_err.txt.gz $l/FW_job.error.gz"
    length=`echo $list | wc -w`
    [[ $length -gt 500 ]] && cd $indir/tmp && htar -xvf garden/${block}.tar $list && list="" && cd -
  done
  [[ ! -z "$list" ]] && cd $indir/tmp && htar -xvf garden/${block}.tar $list && cd -
  nrestored=`ls -1 $indir/tmp/$block | wc -l`
  echo $nlaunchers $nrestored
  [[ ! $nlaunchers -eq $nrestored ]] && echo 'missing launchers!' && exit;
  rm -rv $indir/$block && rm -rv $indir/tmp/$block
  #break
done
