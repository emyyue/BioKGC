import os
import sys
import pprint

import torch

from torchdrug import core
from torchdrug.utils import comm
from torch.utils import data as torch_data
from torchdrug import data, core, utils
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from nbfnet import dataset, layer, model, task, util#, reasoning_mod
import numpy as np
import pickle


def solver_load(checkpoint, load_optimizer=True):

    if comm.get_rank() == 0:
        logger.warning("Load checkpoint from %s" % checkpoint)
    checkpoint = os.path.expanduser(checkpoint)
    state = torch.load(checkpoint, map_location=solver.device)
    # some issues with loading back the fact_graph and graph
    # remove
    state["model"].pop("fact_graph")
    state["model"].pop("graph")
    state["model"].pop("undirected_fact_graph")
    # load without
    solver.model.load_state_dict(state["model"], strict=False)


    if load_optimizer:
        solver.optimizer.load_state_dict(state["optimizer"])
        for state in solver.optimizer.state.values():
            for k, v in state.items():
                if isinstance(v, torch.Tensor):
                    state[k] = v.to(solver.device)

    comm.synchronize()


def build_solver(cfg):
    cfg.task.model.num_relation = _dataset.num_relation
    _task = core.Configurable.load_config_dict(cfg.task)
    cfg.optimizer.params = _task.parameters()
    optimizer = core.Configurable.load_config_dict(cfg.optimizer)
    if "scheduler" in cfg:
        cfg.scheduler.optimizer = optimizer
        scheduler = core.Configurable.load_config_dict(cfg.scheduler)
    else:
        scheduler = None
    return core.Engine(_task, train_set, valid_set, test_set, optimizer, scheduler, **cfg.engine)

def load_vocab(dataset):
    entity_mapping = {}
    with open(vocab_file, "r") as fin:
        for line in fin:
            k, v = line.strip().split("\t")
            entity_mapping[k] = v
    entity_vocab = [entity_mapping[t] for t in dataset.entity_vocab]
    relation_vocab = ["%s (%d)" % (t[t.rfind("/") + 1:].replace("_", " "), i)
                      for i, t in enumerate(dataset.relation_vocab)]
    
    return entity_vocab, relation_vocab

@torch.no_grad()
def get_prediction(cfg, solver, relation_vocab):
    test_set = solver.test_set

    dataloader = data.DataLoader(test_set, solver.batch_size, sampler=None, num_workers=solver.num_worker)
    model = solver.model

    model.eval()
    preds = []
    targets = []
    masks = []
    
    for ith, batch in enumerate(dataloader):

        if solver.device.type == "cuda":
            batch = utils.cuda(batch, device=solver.device)
        logger.warning("Predicting batch %s" % ith)
        pred, (mask, target) = model.predict_and_target(batch, dataset)
        
        preds.append(pred)
        targets.append(target)
        masks.append(mask)
    
    pred = utils.cat(preds)
    target = utils.cat(targets)
    mask = utils.cat(masks)

    
    return pred, target, mask

def pred_to_dataframe(pred, dataset, entity_vocab, relation_vocab):
    # get head nodes
    
    #testset_nodes = [dataset.entity_vocab[i] for i in [x.numpy()[0] for x in solver.test_set]]
    testset_relation =  [relation_vocab[i] for i in [x.numpy()[2] for x in solver.test_set]]
    nodes = dataset.entity_vocab
    node_type = dataset.graph.node_type
    
    # get both relation and relation^(-1)
    dflist=[]
    for j in [0, 1]:
        sigmoid = torch.nn.Sigmoid()
        prob= sigmoid(pred[:, j, :])
        # prob = (pred[:, j, :])
        prob = prob.flatten().cpu().numpy()
        temp = {'query_node': np.repeat([dataset.entity_vocab[i] for i in [x.numpy()[j] for x in solver.test_set]], len(nodes)),
                   'query_relation': np.repeat(testset_relation, len(nodes)),
                   'reverse': j,
                   'pred_node': np.tile(nodes, len(testset_relation)),
                   'pred_node_type': np.tile(node_type, len(testset_relation)),
                   'probability':prob.tolist()}
         
        # mask out unwanted
        mymask = temp['pred_node_type'] == 0
        df_dict = {'query_node': temp['query_node'][mymask],
                   'query_relation': temp['query_relation'][mymask],
                   'reverse': j,
                   'pred_node':  temp['pred_node'][mymask],
                   'pred_node_type':  temp['pred_node_type'][mymask],
                   'probability': prob[mymask]}
           
        dflist.append(df_dict)
    
    df = pd.concat([pd.DataFrame(dflist[0]),pd.DataFrame(dflist[1])])
    lookup = pd.DataFrame(list(zip( dataset.entity_vocab, entity_vocab)), columns =['short', 'long'])

    df = pd.merge(df, lookup, how="left", left_on="query_node", right_on="short", sort=False)
    df = pd.merge(df, lookup, how="left", left_on="pred_node", right_on="short", sort=False)
    return df

def sig(x):
 return 1/(1 + np.exp(-x))

        
if __name__ == "__main__":
    args, vars = util.parse_args()
    cfg = util.load_config(args.config, context=vars)
    working_dir = util.create_working_directory(cfg)
    vocab_file = os.path.join(os.path.dirname(__file__), cfg.dataset.path, "entity_names.txt")
    vocab_file = os.path.abspath(vocab_file)

    torch.manual_seed(args.seed + comm.get_rank())

    logger = util.get_root_logger()
    if comm.get_rank() == 0:
        logger.warning("Config file: %s" % args.config)
        logger.warning(pprint.pformat(cfg))
                 
    cfg.dataset.files = ['train1.txt', 'train2.txt', 'valid.txt', 'test_eval.txt']
    _dataset = core.Configurable.load_config_dict(cfg.dataset)
    train_set, valid_set, test_set = _dataset.split()
    
    full_valid_set = valid_set
    if comm.get_rank() == 0:
        logger.warning(_dataset)
        logger.warning("#train: %d, #valid: %d, #test: %d" % (len(train_set), len(valid_set), len(test_set)))

    solver = build_solver(cfg)

    if "checkpoint" in cfg:
        solver_load(cfg.checkpoint)
    entity_vocab, relation_vocab = load_vocab(_dataset)

    logger.warning("Starting link prediction")
    pred, target, mask = get_prediction(cfg, solver, relation_vocab)
    df = pred_to_dataframe(pred, _dataset, entity_vocab, relation_vocab)
    logger.warning("Link prediction done")
    logger.warning("Format preds into right dictionary format for TxGNN evaluation")

    # format predictions
    df = df.loc[df.reverse==1]
    df = df.loc[df.pred_node_type==4]
    df['query_relation'] = df['query_relation'].str.split(" \(").str[0]
    #df['probability'] = sig(df['probability'])
    
    ##################
    # format node info
    nodes = pd.read_csv(os.path.join(cfg.dataset.path, "entity_all_info.txt"), sep="\t")
    # create lookup dictionaries
    ### for drugs
    drug_map1 = {}
    drug_df = nodes.loc[nodes.node_type=="drug"]
    for i in range(len(drug_df)):
        drug_map1[drug_df.iloc[i,:]['node_name']] = drug_df.iloc[i,:]['node_id']
    ### for diseases
    di_map2 = {}
    di_map1 = {}
    disease_df = nodes.loc[nodes.node_type=="disease"]
    for i in range(len(disease_df)):
        di_map2[disease_df.iloc[i,:]['node_id']] = disease_df.iloc[i,:]['node_name']
        di_map1[disease_df.iloc[i,:]['node_name']] = disease_df.iloc[i,:]['node_id']

    ##################
    for rel in ['contraindication', 'indication', 'off-label use']:
        import pdb; pdb.set_trace()
        df_rel = df.loc[df.query_relation==rel]
        myworkingdir = cfg.output_directory
        obj = pd.read_pickle(os.path.join(myworkingdir, "preds_" + rel +".pickle"))        

        # read in dictionary from TxGNN
        goal = obj.copy()
        # get the txgnn prediction dictionaries
        for dis in goal.keys(): # for each disease in disease area split
            goal[dis] = dict.fromkeys(goal[dis], 0)
            if (dis in di_map2):
                df = pred.loc[(pred.long_x == di_map2[(dis)])]
                print(dis)
                for i in df['long_y']: # for each drug
                    goal[dis][drug_map1[i]] = df.loc[df.long_y == i].iloc[0]['probability']
            elif(dis.split(".")[0] in di_map2):
                dis_m = dis.split(".")[0]
                print(dis_m)
                df = pred.loc[(pred.long_x == di_map2[(dis_m)])]
                for i in df['long_y']:
                    goal[dis][drug_map1[i]] = df.loc[df.long_y == i].iloc[0]['probability']
            else:
                print(f"not found", dis)

                
        # save
        logger.warning("Save dictionary")
        logger.warning(rel)
        filename = os.path.join(myworkingdir, 'preds_' + rel + '_nbfnet.pickle')
        with open(filename, 'wb') as handle: pickle.dump(goal, handle, protocol=pickle.HIGHEST_PROTOCOL)
        