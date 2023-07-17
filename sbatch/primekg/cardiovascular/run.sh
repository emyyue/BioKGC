sbatch --wait << EOF
#!/bin/bash

#SBATCH -J train
#SBATCH --output=job_output_%j.txt
#SBATCH --error=job_error_%j.txt
#SBATCH --time=12:00:00 # takes around 7 hours to run
#SBATCH --mem=64G
#SBATCH -c 2
#SBATCH -w gpusrv62
#SBATCH --gres=gpu:1
#SBATCH -p gpu_p
#SBATCH --qos=gpu
#SBATCH --nice=10000

source $HOME/.bashrc
. /home/icb/samuele.firmani/NBFNet/conda-env/activate_env.sh 

python ../../../script/run.py -c /home/icb/samuele.firmani/NBFNet/config/knowledge_graph/primekg/cardiovascular.yaml --gpus [0] --version v1 --adv_tmp 0.5 --cond_prob yes --neg_samp 32 --agg_fun pna --hidden_layers [32,32,32,32] --epochs 1 --lr 1e-3

EOF
