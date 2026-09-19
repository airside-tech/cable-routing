'''
Dijkstra's algorithm implementation for finding the shortest path in a graph.

The graph should be represented as an adjacency list, where each key is a node
and the corresponding value is a list of tuples representing the neighboring nodes
and the edge weights.

    
    (*)        NODES (VERTICES)
    
    ------     EDGE          //      --- 5 ---   EDGE WEIGHT


     1         2
A --------> B --------> C
|           ^         |
|           |         |
|           5         1
|           |         |
+----------> D <------+
     1


Adjacent list example for a representation of a graph:
graph = {
    'A': [('B', 1), ('C', 4)],
    'B': [('A', 1), ('C', 2), ('D', 5)],
    'C': [('A', 4), ('B', 2), ('D', 1)],
    'D': [('B', 5), ('C', 1)]
}

**************************
Priority queue example:
A priority queue is just like a regular list (array), but each of its elements has an extra value 
to represent their priority. Lowest value = highest prio! This is a sample priority queue:

pq = [(3, "A"), (1, "C"), (7, "D")]

# Convert into a queue object
heapify(pq)

# Return the highest priority value
heappop(pq)     ---> (1, 'C')

heappush(pq, (0, "B"))

heappop(pq) --> (0, "B")        NOTE; (0, "B") is then no longer part of the queue!

**************************

REFERENCE:
https://www.datacamp.com/tutorial/dijkstra-algorithm-in-python?utm_cid=23781701478&utm_aid=196565213035&utm_campaign=260417_1-ps-dscia~amx-tofu~python_2-b2c_3-emea_4-prc_5-na_6-na_7-le_8-pdsh-go_9-nb-e_10-na_11-na&utm_loc=9221766-&utm_mtd=p-c&utm_kw=dijkstra%20algorithm%20python&utm_source=google&utm_medium=paid_search&utm_content=ps-dscia~emea-en~amx~tofu~tutorial~python&gad_source=1&gad_campaignid=23781701478&gbraid=0AAAAADQ9WsFpmVu8a04Q8Gt7wQ-zVVuQe&gclid=CjwKCAjw2aPVBhBkEiwA0Cptt8F-B4nlHWMWVU7li86rjvzhHQ2LzZ9LiVQhdwR6i5d1UD1xp70lXxoCO-IQAvD_BwE

'''

from heapq import heapify, heappop, heappush  # Required to work with priority queues!
'''
heapify: Turns a list of tuples with priority-value pairs into a priority queue.
heappush: Adds an element to the queue with its associated priority.
heappop: Removes and returns the element with the highest priority (the element with the smallest value).
'''

class Graph:
    
    def __init__(self, graph: dict = {}):
        self.graph = graph  # A dictionary for the adjacency list


    def add_edge(self, node1, node2, weight):
        if node1 not in self.graph:  # Check if the node is already added
            self.graph[node1] = {}  # If not, create the node
        self.graph[node1][node2] = weight  # Else, add a connection to its neighbor

    def shortest_distances(self, source_node: str):
        '''
        Initialize distances to all nodes except source node as infinity.
        The distance to the source node is 0 
        '''
        distances = {node: float("inf") for node in self.graph} # dict with node-value-pairs
        distances[source_node] = 0
        predecessors = {node: None for node in self.graph}
    
        '''
        We need a way to iterate over graph nodes and to sort them, so a priority queue is better than
        iteration over arrays here. In each iteration: choose the node with the smallest value and
        visit its neighbors.
        
        Initialize the queue (The priority of each element inside pq will be its current value):
        '''
        pq = [(0,source_node)]
        heapify(pq)
        
        # Create a set to hold the visited nodes:
        visited = set()

        while pq:  # While the priority queue isn't empty
            current_distance, current_node = heappop(pq)  # Get the node with the min distance

            if current_node in visited:
                continue  # Skip already visited nodes
            visited.add(current_node)  # Else, add the node to visited set
                   
            for neighbor, weight in self.graph[current_node].items():
                # Calculate the distance from current_node to the neighbor
                tentative_distance = current_distance + weight
                if tentative_distance < distances[neighbor]:
                    distances[neighbor] = tentative_distance
                    predecessors[neighbor] = current_node
                    heappush(pq, (tentative_distance, neighbor))

        return distances, predecessors
        
        


    def shortest_path(self, source: str, target: str):
        # Generate the predecessors dict
        distances, predecessors = self.shortest_distances(source)

        if distances[target] == float("inf"):
            return []

        path = []
        current_node = target

        # Backtrack from the target node using predecessors
        while current_node:
            path.append(current_node)
            current_node = predecessors[current_node]

        # Reverse the path and return it
        path.reverse()

        return path


def test_graphs(graph:dict, source_node:str, target_node:str):
    network = Graph(graph)
            
    path = network.shortest_path(source_node, target_node)
    print(f"The shortest path from {source_node} to {target_node} is {path}")
    
    distances, predecessors = network.shortest_distances(source_node)
    print(f"The shortest distances from {source_node} to {target_node} are {distances} and with predecessors {predecessors}")
        
        

def main():
    
    graph1 = {
    'A': {'B': 3, 'D': 3},
    'B': {'A': 3, 'C': 2, 'D': 4},
    'C': {'B': 2, 'D': 1},
    'D': {'A': 3, 'B': 4, 'C': 1}
    }

    graph2 = {
    "A": {"B": 3, "C": 3},
    "B": {"A": 3, "D": 3.5, "E": 2.8},
    "C": {"A": 3, "E": 2.8, "F": 3.5},
    "D": {"B": 3.5, "E": 3.1, "G": 10},
    "E": {"B": 2.8, "C": 2.8, "D": 3.1, "G": 7},
    "F": {"G": 2.5, "C": 3.5},
    "G": {"F": 2.5, "E": 7, "D": 10},
    } 
    
    test_graphs(graph1, "A", "C")
    

if __name__ == "__main__":
    main()
    

