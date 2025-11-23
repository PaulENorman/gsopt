#this file is used to test gsopt.py by sending optimization requests with known functions
import requests
import numpy as np
import matplotlib.pyplot as plt
import time
import os
from typing import Callable, List, Dict, Tuple, Optional

# --- Configuration ---
BASE_URL = 'http://localhost:8080'
NUM_ITERATIONS = 20
BATCH_SIZE = 5
NUM_INIT_POINTS = 10
NOISE_LEVEL = 0.01

# List of optimizers to test
OPTIMIZERS = ['NEVERGRAD-OnePlusOne', 'SKOPT-GP']

# --- Benchmark Functions ---

def sphere(x: np.ndarray) -> float:
    """Sphere function. Minimum is 0 at x_i = 0."""
    return np.sum(x**2)

def rosenbrock(x: np.ndarray) -> float:
    """Rosenbrock function. Minimum is 0 at x_i = 1."""
    return np.sum(100.0 * (x[1:] - x[:-1]**2.0)**2.0 + (1 - x[:-1])**2.0)

def ackley(x: np.ndarray) -> float:
    """Ackley function. Minimum is 0 at x_i = 0."""
    n = len(x)
    sum1 = np.sum(x**2)
    sum2 = np.sum(np.cos(2.0 * np.pi * x))
    term1 = -20.0 * np.exp(-0.2 * np.sqrt(sum1 / n))
    term2 = -np.exp(sum2 / n)
    return term1 + term2 + 20.0 + np.e

def branin(x: np.ndarray) -> float:
    """Branin function (2D only). Minimum is ~0.397887."""
    x1, x2 = x
    a = 1.0
    b = 5.1 / (4.0 * np.pi**2)
    c = 5.0 / np.pi
    r = 6.0
    s = 10.0
    t = 1.0 / (8.0 * np.pi)
    term1 = a * (x2 - b * x1**2 + c * x1 - r)**2
    term2 = s * (1 - t) * np.cos(x1)
    return term1 + term2 + s

def linear_with_noise(x: np.ndarray) -> float:
    """Linear function with noise. Minimum is at the lower bound."""
    # Coefficients for the linear function, e.g., [1, -2]
    coeffs = np.array([1, -2][:len(x)])
    return np.dot(coeffs, x) + np.random.normal(0, NOISE_LEVEL)

def parabolic_with_noise(x: np.ndarray) -> float:
    """Parabolic function (Sphere) with noise. Minimum is ~0 at x_i = 0."""
    return np.sum(x**2) + np.random.normal(0, NOISE_LEVEL)


# --- Test Runner ---

def run_test(
    func: Callable,
    name: str,
    dims: int,
    bounds: Tuple[float, float],
    true_minimum: float,
    optimizer_type: str = 'GP'
) -> Tuple[List[int], List[float]]:
    """
    Runs a full optimization test for a given function with a specific optimizer.

    Args:
        func: The objective function to test.
        name: The name of the function for plotting and logging.
        dims: The number of dimensions for the function.
        bounds: A tuple (min, max) for all dimensions.
        true_minimum: The known true minimum of the function.
        optimizer_type: The type of optimizer to use ('GP', 'SNOBFIT', etc.)
        
    Returns:
        Tuple of (evaluations_list, best_results_list) for plotting
    """
    print(f"\n--- Running test for: {name} with {optimizer_type} ---")
    start_time = time.time()

    param_names = [f'x{i+1}' for i in range(dims)]
    settings = {
        "base_estimator": optimizer_type,
        "acquisition_function": "EI",
        "num_params": dims,
        "param_names": param_names,
        "param_mins": [bounds[0]] * dims,
        "param_maxes": [bounds[1]] * dims,
        "num_init_points": NUM_INIT_POINTS,
        "batch_size": BATCH_SIZE
    }

    # 1. Initialize Optimization
    try:
        response = requests.post(
            f'{BASE_URL}/init-optimization',
            json={"settings": settings},
            headers={"X-User-Email": "test@gmail.com"}
        )
        response.raise_for_status()
        points_to_evaluate = response.json()['data']
    except requests.RequestException as e:
        print(f"Error initializing optimization: {e}")
        return [], []

    all_evaluated_points = []
    best_results_over_time = []
    num_evaluations = []
    current_best = float('inf')
    total_evals = 0

    # Main optimization loop
    for i in range(NUM_ITERATIONS):
        print(f"Iteration {i+1}/{NUM_ITERATIONS}... ({len(points_to_evaluate)} points)")

        # 2. Evaluate points
        evaluated_this_iteration = []
        for point in points_to_evaluate:
            params = np.array([point[name] for name in param_names])
            objective_value = func(params)
            point['objective'] = objective_value
            evaluated_this_iteration.append(point)
            
            total_evals += 1
            
            if objective_value < current_best:
                current_best = objective_value
            
            # Track best result after each evaluation
            num_evaluations.append(total_evals)
            best_results_over_time.append(current_best)
        
        all_evaluated_points.extend(evaluated_this_iteration)

        # 3. Continue Optimization
        try:
            response = requests.post(
                f'{BASE_URL}/continue-optimization',
                json={"settings": settings, "existing_data": all_evaluated_points},
                headers={"X-User-Email": "test@gmail.com"}
            )
            response.raise_for_status()
            points_to_evaluate = response.json()['data']
        except requests.RequestException as e:
            print(f"Error during continue-optimization: {e}")
            break
    
    print(f"Test finished. Best minimum found: {current_best:.4f}")
    print(f"Total evaluations: {total_evals}")
    print(f"Total time: {time.time() - start_time:.2f}s")

    return num_evaluations, best_results_over_time

def compare_optimizers(
    func: Callable,
    name: str,
    dims: int,
    bounds: Tuple[float, float],
    true_minimum: float,
    optimizers: List[str] = None
):
    """
    Compares multiple optimizers on the same function.
    
    Args:
        func: The objective function to test
        name: The name of the function for plotting
        dims: The number of dimensions
        bounds: A tuple (min, max) for all dimensions
        true_minimum: The known true minimum of the function
        optimizers: List of optimizer types to compare
    """
    if optimizers is None:
        optimizers = OPTIMIZERS
    
    plt.figure(figsize=(12, 7))
    
    for optimizer_type in optimizers:
        num_evals, best_results = run_test(func, name, dims, bounds, true_minimum, optimizer_type)
        if num_evals:  # Only plot if we got results
            plt.plot(num_evals, best_results, marker='o', label=f'{optimizer_type}', alpha=0.7, markersize=3)
    
    # plt.axhline(y=true_minimum, color='r', linestyle='--', linewidth=2, label=f'True Minimum ({true_minimum})')
    plt.xlabel('Number of Objective Function Evaluations', fontsize=12)
    plt.ylabel('Best Objective Value Found', fontsize=12)
    plt.title(f'Optimizer Comparison: {name} Function', fontsize=14)
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.yscale('log')  # Log scale often helps visualize convergence
    
    output_dir = "test_results"
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f'{name.lower().replace(" ", "_")}_comparison.png')
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"\nComparison plot saved to {filename}\n")
    plt.close()


if __name__ == "__main__":
    # Define the tests to run
    tests = [
        {"func": sphere, "name": "Sphere", "dims": 3, "bounds": (-5, 5), "min": 0.0},
        {"func": rosenbrock, "name": "Rosenbrock", "dims": 3, "bounds": (-2, 2), "min": 0.0},
        {"func": ackley, "name": "Ackley", "dims": 3, "bounds": (-5, 5), "min": 0.0},
        {"func": parabolic_with_noise, "name": "Parabolic with Noise", "dims": 3, "bounds": (-5, 5), "min": 0.0},
    ]

    for test in tests:
        compare_optimizers(
            func=test['func'],
            name=test['name'],
            dims=test['dims'],
            bounds=test['bounds'],
            true_minimum=test['min'],
            optimizers=OPTIMIZERS
        )
