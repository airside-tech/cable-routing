'''
Another version of the Dijkstra implementation
- From book "grokking algorithms"


This version of the algorithm (chapter 7) uses three hash tables (chapter 5)
- A hash function is a function where we put in a string and get back a number.
- "C" --> 5 as an example
- The hash tables and a "dict" is the same, --> myHash = dict() <---> myHash= {}

This version of the algorithm does not use a priority queue.

The hash tables are:
-   graph
-   costs
-   parents


 EXAMPLE GRAPH used (Note: hash table with hash tables inside!!);
graph = 
        {
        'start': {'a': 6, 'b': 2},
        'a': {'fin': 1},                --> graph ["a"] = {},  graph["a"]["fin"] =  1
        'b': {'a': 3, 'fin': 5},
        'fin': {}                       --> the FINISH node does not have neighbors
        }


'''

# Global definition
infinity = float("inf")


class Graph_v2:

    def __init__(self, graph: dict = {}, costs: dict = {}, parents: dict = {}):
        # The nodes, edges and the weights of the edges --> adjacency list (static):
        self.graph = graph
        
        # We will iterate and sort using a costs hash table (dynamic) 
        self.costs = costs
        
        # and a parents hash table (dynamic):
        self.parents = parents
        
        # Finally, we need to keep track of the nodes that have been processed:
        self.processed = []


        # Algorithm:
        node = self.find_lowest_cost_node(self.costs) # find the lowest cost node that is unprocessed (i.e. b = 2)

        # Continue until all nodes are processed
        while node is not None:
            cost = self.costs[node]         # using the next node
            neighbors = self.graph[node]    # i.e. grab the node B's hash table for the neighbors {a:3, fin: 5}
            
            # Go through all neighbors of this node (list of nodes..[])
            # neighbors.keys --> node names
            for n in neighbors.keys():      
                new_cost = cost + neighbors[n]   # "Cost of b, i.e. 2, neighbors[n]"
                
                # If it is cheaper to get to this neighbor by going through this node
                if self.costs[n] > new_cost:
                    # Then update the cost for this node
                    self.costs[n] = new_cost
                    
                    #.. and promote the node as new parent for this neighbor
                    self.parents[n] = node
            
            # Mark the node as processed
            self.processed.append(node)
            
            # Select next lowest cost, unprocessed node for the loop
            node = self.find_lowest_cost_node(self.costs)
              


    def find_lowest_cost_node(self, costs):
        lowest_cost = float("inf")  # initialize at infinity, none processed
        lowest_cost_node = None     # The node initial starting node as 0 cost
        
        # Go through each node
        for node in costs:
            cost = costs[node]
            
            # lowest cost so far and not yet processed?
            if cost < lowest_cost and node not in self.processed:
                # set it as the new lowest cost node
                lowest_cost = cost 
                lowest_cost_node = node

        return lowest_cost_node
     
    
    
    
    
    

def main():
    # Basic testing of this class
    
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


    G= Graph_v2(graph, costs, parents)

    #Which nodes were processed?
    print(G.processed)
    print(G.costs)

if __name__ == "__main__":
    main()
    
    
