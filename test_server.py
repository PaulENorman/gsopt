#this file is used to test server funcitonality by sentding post requests to 8080

import requests
import time
import os

dimensions = {'x1': (-5, 5), 'x2': (-5, 5)}
batch_size = 50
acq_func = 'EI'
base_estimator = 'GP'

json = {
    'dimensions': dimensions,
    'base_estimator': base_estimator,
    'acq_func': acq_func,
    'batch_size': batch_size
}

def start_optimization():
    os.remove('gsopt_cache.csv')
    response = requests.post('http://localhost:8080/start-optimization', json=json)
    
    print("Start Optimization Response:", response.json())

def simulate_user_input():
    response = requests.post('http://localhost:8080/simulate-user-input', json=json)
                             
    print("Simulate User Input Response:", response.json())

def continue_optimization():
    response = requests.post('http://localhost:8080/continue-optimization', json=json)
    print("Continue Optimization Response:", response.json())

if __name__ == "__main__":
    print("Testing optimization server...")
    start = time.time()
    start_optimization()
    print("Time taken to start optimization:", time.time() - start)
    #for i in range(10):
    #    simulate_user_input()
    #    continue_optimization()