'''
Dijkstra's algorithm implementation for finding the shortest path in a graph.

The graph should be represented as an adjacency list, where each key is a node
and the corresponding value is a list of tuples representing the neighboring nodes
and the edge weights.

Example:
graph = {
    'A': [('B', 1), ('C', 4)],
    'B': [('A', 1), ('C', 2), ('D', 5)],
    'C': [('A', 4), ('B', 2), ('D', 1)],
    'D': [('B', 5), ('C', 1)]
}


TODO: Implement Dijkstra's algorithm for the Graph class.
https://www.datacamp.com/tutorial/dijkstra-algorithm-in-python?utm_cid=23781701478&utm_aid=196565213035&utm_campaign=260417_1-ps-dscia~amx-tofu~python_2-b2c_3-emea_4-prc_5-na_6-na_7-le_8-pdsh-go_9-nb-e_10-na_11-na&utm_loc=9221766-&utm_mtd=p-c&utm_kw=dijkstra%20algorithm%20python&utm_source=google&utm_medium=paid_search&utm_content=ps-dscia~emea-en~amx~tofu~tutorial~python&gad_source=1&gad_campaignid=23781701478&gbraid=0AAAAADQ9WsFpmVu8a04Q8Gt7wQ-zVVuQe&gclid=CjwKCAjw2aPVBhBkEiwA0Cptt8F-B4nlHWMWVU7li86rjvzhHQ2LzZ9LiVQhdwR6i5d1UD1xp70lXxoCO-IQAvD_BwE

'''


class Graph:
   def __init__(self, graph: dict = {}):
       self.graph = graph  # A dictionary for the adjacency list

   def add_edge(self, node1, node2, weight):
       if node1 not in self.graph:  # Check if the node is already added
           self.graph[node1] = {}  # If not, create the node
       self.graph[node1][node2] = weight  # Else, add a connection to its neighbor



