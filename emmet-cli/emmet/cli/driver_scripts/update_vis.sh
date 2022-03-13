source /home/mwu/anaconda3/etc/profile.d/conda.sh
conda activate mpcite
python /home/mwu/emmet/emmet-cli/emmet/cli/driver_scripts/update_vis.py 
conda deactivate;
echo visualization updated.
