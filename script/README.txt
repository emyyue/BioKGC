# 1. Run NBFNet:
python script/run.py -c config/knowledge_graph/mockdata.yaml --gpus [0]

# 2. Visualize:
python script/visualize_graph.py -c config/knowledge_graph/mockdata_viz.yaml --gpus [0]  --checkpoint YOUR_MODEL_PTH

# 3. Predict: 
create new test.txt with all nodes and relations you are interested in
script will predict each query (node + relation) against every other node
take the top 3 predictions

python script/predict.py -c config/knowledge_graph/mockdata_viz.yaml --gpus [0]  --checkpoint YOUR_MODEL_PTH

In the following example (for test.txt), predictions will be made for 
- p(?|pathway15, GO:annotation)
- p(?|gene4, GO:annotation-1)
- p(?|gene2, up)
- p(?|gene1, up-1)

example of test.txt
"""
pathway15	GO:annotation	gene4
gene2	up	gene1
"""
