#!/usr/bin/env bash  
PATH=/global/homes/h/huck/bin:/global/homes/m/mwu1011/anaconda3/envs/lbnl/bin:/global/homes/m/mwu1011/anaconda3/condabin:/opt/cray/pe/mpt/7.7.10/gni/bin:/opt/cray/rca/2.2.20-7.0.1.1_4.61__g8e3fb5b.ari/bin:/opt/cray/alps/6.6.58-7.0.1.1_6.19__g437d88db.ari/sbin:/opt/cray/alps/default/bin:/opt/cray/job/2.2.4-7.0.1.1_3.47__g36b56f4.ari/bin:/opt/cray/pe/craype/2.6.2/bin:/opt/intel/compilers_and_libraries_2019.3.199/linux/bin/intel64:/usr/common/software/darshan/3.2.1/bin:/global/common/cori/software/altd/2.0/bin:/usr/common/software/bin:/usr/common/nsg/bin:/opt/ovis/bin:/opt/ovis/sbin:/opt/cray/pe/modules/3.2.11.4/bin:/usr/local/bin:/usr/bin:/bin:/usr/lib/mit/bin:/usr/lib/mit/sbin:/opt/cray/pe/bin


# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/global/homes/m/mwu1011/anaconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/global/homes/m/mwu1011/anaconda3/etc/profile.d/conda.sh" ]; then
        . "/global/homes/m/mwu1011/anaconda3/etc/profile.d/conda.sh"
    else
        export PATH="/global/homes/m/mwu1011/anaconda3/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<
source ~/.bashrc

conda activate base;
module load esslurm;
emmet --sbatch --yes --run --issue 87 tasks -d $SCRATCH/projects clear-uploaded
