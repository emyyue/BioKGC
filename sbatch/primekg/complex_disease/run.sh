sbatch --wait << EOF
#!/bin/bash

#SBATCH -J train
#SBATCH --output=/home/icb/samuele.firmani/NBFNet/sbatch/primekg/complex_disease/logs/job_output_%j.txt
#SBATCH --error=/home/icb/samuele.firmani/NBFNet/sbatch/primekg/complex_disease/error_logs/job_error_%j.txt
#SBATCH --time=20:00:00 # takes around 7 hours to run
#SBATCH --mem=64G
#SBATCH -c 2
#SBATCH --gres=gpu:1
#SBATCH -p gpu_p
#SBATCH --qos=gpu
#SBATCH --nice=10000

source $HOME/.bashrc
. /home/icb/samuele.firmani/NBFNet/conda-env/activate_env.sh 

python /home/icb/samuele.firmani/NBFNet/script/run.py -c /home/icb/samuele.firmani/NBFNet/config/knowledge_graph/primekg/complex_disease.yaml --gpus [0] --version v1 --adv_tmp 0.5 --cond_prob yes --neg_samp 64 --agg_fun pna --hidden_layers [32,32,32,32,32,32] --epochs 10 --lr 1e-3

EOF
