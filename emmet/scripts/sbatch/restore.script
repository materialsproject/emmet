#!/bin/bash -l
#SBATCH --qos=xfer
#SBATCH --time=48:00:00
#SBATCH --job-name=restore
#SBATCH --licenses=SCRATCH
#SBATCH --mail-user=phuck@lbl.gov
#SBATCH --mail-type=ALL
#SBATCH --output=restore-%j.out
#SBATCH --error=restore-%j.error

cwd=$PWD

#outdir=/global/cscratch1/sd/huck/tasks_from_old_prod_2019/
#dirlist="/global/homes/h/huck/mp_prod/workdir/tasks_from_old_prod_2019/restore.txt"

[[ ! -d $outdir ]] && mkdir -pv $outdir
chown -v huck:matgen $outdir
cd $outdir && pwd
files="INCAR CONTCAR KPOINTS POSCAR POTCAR vasprun.xml OUTCAR"
blocks=`cut -d/ -f1 $dirlist | sort -u`
echo $blocks | wc -w

for block in $blocks; do
  echo $block

  filelist=""
  for launcher in `grep $block $dirlist`; do
    for file in $files; do
      filelist="$filelist $launcher/$file*"
    done
    length=`echo $filelist | wc -w`
    if [ $length -gt 1000 ]; then
      htarlist=`htar -tf garden/$block.tar $filelist | awk '{ print $7 }' | grep $block`
      [[ $? -ne 0 ]] && echo 'error in htar -tf' && exit
      list=""
      for l in $htarlist; do
	[[ ! -e $l ]] && echo "$l does not exist" && list="$list $l"
      done
      if [ ! -z "$list" ]; then
	echo restore `echo $list | wc -w`
	htar -xvf garden/${block}.tar $list
	list=""
      fi
      filelist=""
    fi
  done

  if [ ! -z "$filelist" ]; then
    htarlist=`htar -tf garden/$block.tar $filelist | awk '{ print $7 }' | grep $block`
    [[ $? -ne 0 ]] && echo 'error in htar -tf' && exit
    list=""
    for l in $htarlist; do
      [[ ! -e $l ]] && echo "$l does not exist" && list="$list $l"
    done
    if [ ! -z "$list" ]; then
      echo restore remaining `echo $list | wc -w`
      htar -xvf garden/${block}.tar $list
    fi
  fi

  parallel -0m 'chmod -v g+rw {}' :::: <(find $block -not -perm -660 -print0)
  [[ $? -ne 0 ]] && echo 'error in chmod' && exit
  parallel -0m 'chown -v huck:matgen {}' :::: <(find $block -not -group matgen -print0)
  [[ $? -ne 0 ]] && echo 'error in chown' && exit
  #break
done

cd $cwd
echo DONE
