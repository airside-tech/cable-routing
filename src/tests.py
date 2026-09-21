from dijkstra_v1 import Graph_v1
from dijkstra_v2 import Graph_v2
from time import time

infinity = float("inf")


def test_dijkstra_v1(graph, source_node, target_node):
    
    G1 = Graph_v1(graph)
    
    
    path = G1.shortest_path(source_node, target_node)
    print(f"The shortest path from {source_node} to {target_node} is {path}")
    
    distances, predecessors = G1.shortest_distances(source_node)
    print(f"The shortest distances from {source_node} to {target_node} are {distances} and with predecessors {predecessors}\n")
        
    


def test_dijkstra_v2(graph, source_node, target_node):
    graph = {
                'start': {'a': 6, 'b': 2},
                'a': {'fin': 1},                
                'b': {'a': 3, 'fin': 5},
                'fin': {}                    
            }
    
    costs = {
            'a':6, 'b':2, 'fin':infinity  # We do not know the cost to the finish, only some estimates
        }
    
    parents = {
            'a':'start', 'b':'start', 'fin':None    
        }
    
    G2 = Graph_v2(graph, costs, parents)
    




def main():
    graph = {
        'start': {'a': 6, 'b': 2},
        'a': {'fin': 1},                
        'b': {'a': 3, 'fin': 5},
        'fin': {}                    
        }
    
    source_node = 'start'
    target_node = 'fin'
    
    tick = time()
    test_dijkstra_v1(graph, source_node, target_node)
    tock = time()
    
    processed_time = tock - tick
    print(f"dijkstra_v1.py used {processed_time:.5f} seconds to complete\n")
    
    tick = time()
    test_dijkstra_v2(graph, source_node, target_node)
    tock = time()
    
    processed_time = tock - tick
    print(f"dijkstra_v2.py used {processed_time:.5f} seconds to complete\n")
    
    

if __name__ == "__main__":
    main()
    
    

