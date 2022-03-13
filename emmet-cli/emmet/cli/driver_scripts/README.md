## Overall process slides
https://docs.google.com/presentation/d/1I9Tg9KZ-gRzumjRguyQa3U6NXJaPjrteMdZ1PCTp76c/edit?usp=sharing

## To configure automatic upload to GDrive & NOMAD
0. install rclone
    - please name the rclone instance `GDriveUpload`
    - Test usage:
        - `rclone --log-level INFO -c --auto-confirm copy DIRECTORY GDriveUpload:`
        - More help on Rclone [Documentation](https://rclone.org/commands/rclone_copy/)
1. set Cronjob
    - Open Cronjob settings page using `crontab -e`
    - Copy and paste the following lines into the settings page
    - `0 */24 * * * /usr/bin/env bash -l '/global/homes/m/mwu1011/projects/emmet/emmet-cli/emmet/cli/driver_scripts/run.sh' >> /global/homes/m/mwu1011/projects/driver_scripts/output.txt`
    - `0 6,12,18 * * * /usr/bin/env bash -l '/global/homes/m/mwu1011/projects/emmet/emmet-cli/emmet/cli/driver_scripts/run_nomad.sh' >> /global/homes/m/mwu1011/projects/driver_scripts/output_nomad.txt`
    - `0 17 * * * /usr/bin/env bash -l '/global/homes/m/mwu1011/projects/emmet/emmet-cli/emmet/cli/driver_scripts/run_clear.sh' >> /global/homes/m/mwu1011/projects/driver_scripts/output_clear_uploaded.txt`
    - Change directory referenced as needed
    - use [https://crontab.guru/](https://crontab.guru/) for changing the time
   
2. make sure the `.sh` files have the correct hyper parameter
    - for `run.sh`, we are uploading the GDrive. As of writing this readme, google limit 750 GB of upload everyday. 
        - `5400` materials roughly leads to about 650 GB of data, leaving 100 GB for tolerance
        - Running this job every 24 hours
    - for `run_nomad.sh`
        - upload a maximum of 320 GB of data with 10 thead (each thread has 10 GB). 
        - put `-1` to indicate this limit, otherwise, it will upload N number of tasks
        - Run this job only at 0600, 1200, 1800. 
    - for `run_clear.sh`
        - Run this everyday at 1700 to reduce the amount of files exists in `$SCRATCH` directory.
        
3. Set up visualization on Matgen server
    - clone the repo & set up environment
    - example cronjob:
        - `0 */3 * * * /usr/bin/env bash -c '/home/mwu/emmet/emmet-cli/emmet/cli/driver_scripts/update_vis.sh' >> /home/mwu/emmet_vis_output.txt`
        