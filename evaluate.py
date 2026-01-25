"""
This script evaluates the performance of different Bayesian optimization strategies
implemented in `gsopt.py`. It does this by running optimization trials on a set of
well-known benchmark functions with known theoretical minima.

The script supports comparing:
1.  Different surrogate models (regressors) like Gaussian Processes, Random Forests, etc.
2.  Different acquisition functions for a given surrogate model (e.g., EI, LCB).

For each test, it simulates a client-server interaction with the Flask application
in `gsopt.py` using its test client. This ensures that the stateless nature of the
API is respected.

Results are plotted and saved as PNG images in the 'test_results/' directory,
showing the convergence of the best-found objective value over the number of
function evaluations.
"""
import requests
import numpy as np
import matplotlib.pyplot as plt
import time
import os
from typing import Callable, List, Dict, Tuple, Optional, Any

# Import the Flask app from gsopt.py to use its test client
from gsopt import app as flask_app

# Set a seed for reproducibility of random operations
np.random.seed(42)

# --- Global Configuration ---
BASE_URL = 'http://localhost:8080'
NUM_ITERATIONS = 40       # Number of optimization loops after initial points
NOISE_LEVEL = 0.01       # Standard deviation of Gaussian noise to add to the objective
N_DIMS = 5               # Number of dimensions for the benchmark functions
NUM_RUNS = 5             # Number of times to run each optimizer to average results
NUM_INIT_POINTS = N_DIMS*4
BATCH_SIZE = N_DIMS

# List of optimizer identifiers to be tested
OPTIMIZERS: List[str] = ['SKOPT-GP', 'SKOPT-RF', 'SKOPT-ET', 'SKOPT-GBRT', 'RANDOM']


# --- Benchmark Functions ---
# These are standard mathematical functions used to test optimization algorithms.
def sphere(x: np.ndarray) -> float:
    """
    Sphere function. A simple quadratic function.
    The global minimum is 0 at x_i = 0 for all i.
    """
    return np.sum((x - 0.4)**2)

def rosenbrock(x: np.ndarray) -> float:
    """
    Rosenbrock function. A classic non-convex function with a narrow,
    parabolic-shaped valley.
    The global minimum is 0 at x_i = 1 for all i.
    """
    return np.sum(100.0 * (x[1:] - x[:-1]**2.0)**2.0 + (1 - x[:-1])**2.0)

def ackley(x: np.ndarray) -> float:
    """
    Ackley function. A function with many local minima, making it challenging
    for optimizers to find the global minimum.
    The global minimum is 0 at x_i = 0 for all i.
    """
    n = len(x)
    sum1 = np.sum(x**2)
    sum2 = np.sum(np.cos(2.0 * np.pi * x))
    term1 = -20.0 * np.exp(-0.2 * np.sqrt(sum1 / n))
    term2 = -np.exp(sum2 / n)
    return term1 + term2 + 20.0 + np.e

def linear(x: np.ndarray) -> float:
    """
    Linear function. A simple hyperplane.
    The minimum is at the lower bound of the search space.
    """
    coeffs = np.ones(len(x))
    return np.dot(coeffs, x)

def rastrigin(x: np.ndarray) -> float:
    """
    Rastrigin function. Highly multimodal with a regular grid of local minima.
    The global minimum is 0 at x_i = 0 for all i.
    """
    n = len(x)
    return 10 * n + np.sum(x**2 - 10 * np.cos(2 * np.pi * x))

def griewank(x: np.ndarray) -> float:
    """
    Griewank function. Has a product term that introduces dependencies
    between variables.
    The global minimum is 0 at x_i = 0 for all i.
    """
    sum_term = np.sum(x**2) / 4000.0
    prod_term = np.prod(np.cos(x / np.sqrt(np.arange(1, len(x) + 1))))
    return sum_term - prod_term + 1.0

def schwefel(x: np.ndarray) -> float:
    """
    Schwefel function. The global minimum is far from the next best local minimum.
    The global minimum is 0 at x_i = 420.9687 for all i.
    """
    n = len(x)
    # The constant 418.9829 is derived from the location of the minimum.
    return 418.9829 * n - np.sum(x * np.sin(np.sqrt(np.abs(x))))

# --- Third-order polynomial with random coefficients ---
# Coefficients are generated once and reused for consistency across tests.
POLY_COEFFS: Dict[str, np.ndarray] = {
    'a': np.random.uniform(-0.1, 0.1, N_DIMS),
    'b': np.random.uniform(-1, 1, N_DIMS),
    'c': np.random.uniform(-5, 5, N_DIMS)
}

def polynomial_3(x: np.ndarray) -> float:
    """A third-order polynomial with randomly generated coefficients."""
    a, b, c = POLY_COEFFS['a'], POLY_COEFFS['b'], POLY_COEFFS['c']
    return np.sum(a * x**3 + b * x**2 + c * x)


def clear_existing_plots(directory: str = "test_results") -> None:
    """Deletes all .png files in the specified directory before a test run."""
    if not os.path.isdir(directory):
        print(f"Directory '{directory}' not found, skipping plot cleanup.")
        return
    
    print(f"Clearing existing plots in '{directory}'...")
    for filename in os.listdir(directory):
        if filename.endswith(".png"):
            file_path = os.path.join(directory, filename)
            try:
                os.remove(file_path)
                print(f"  Deleted {filename}")
            except Exception as e:
                print(f"  Error deleting {filename}: {e}")
    print("Cleanup complete.\n")


# --- Test Execution Logic ---

def run_test(
    func: Callable[[np.ndarray], float],
    name: str,
    dims: int,
    bounds: Tuple[float, float],
    true_minimum: float,
    optimizer_type: str = 'GP',
    override_settings: Optional[Dict[str, Any]] = None
) -> Tuple[List[int], List[float]]:
    """
    Runs a full optimization test for a given function and optimizer.

    This function simulates the entire optimization process, including initialization
    and iterative steps, by making requests to a test client of the Flask app.
    This ensures that each request is handled statelessly, mimicking a real-world
    API interaction.

    A special path is included for 'RANDOM' search, which is performed locally
    as it doesn't require a backend model.

    Returns:
        A tuple containing:
        - A list of evaluation counts.
        - A list of the best objective value found up to that evaluation.
    """
    # Determine the effective optimizer type for logging and handling special cases.
    effective_optimizer_type = optimizer_type
    if override_settings and 'base_estimator' in override_settings:
        effective_optimizer_type = override_settings['base_estimator']

    print(f"\n--- Running test for: {name} with {effective_optimizer_type} ---")
    start_time = time.time()

    # --- Special case for Random Search (no backend model needed) ---
    if effective_optimizer_type == 'RANDOM':
        param_names = [f'x{i+1}' for i in range(dims)]
        best_results_over_time: List[float] = []
        num_evaluations: List[int] = []
        current_best = float('inf')
        total_evals = 0

        # Define search space bounds for random sampling.
        mins = bounds[0] if isinstance(bounds[0], list) else [bounds[0]] * dims
        maxes = bounds[1] if isinstance(bounds[1], list) else [bounds[1]] * dims

        # Perform initial random sampling.
        num_points_this_iter = NUM_INIT_POINTS
        for i in range(NUM_ITERATIONS + 1):  # +1 to include initial points
            print(f"Iteration {i}/{NUM_ITERATIONS}... ({num_points_this_iter} points)")
            for _ in range(num_points_this_iter):
                params = np.array([np.random.uniform(mins[d], maxes[d]) for d in range(dims)])
                true_val = func(params)
                noisy_val = true_val + np.random.normal(0, NOISE_LEVEL)
                
                total_evals += 1
                if true_val < current_best:
                    current_best = true_val
                num_evaluations.append(total_evals)
                best_results_over_time.append(current_best)
            
            # Subsequent iterations use the standard batch size.
            num_points_this_iter = BATCH_SIZE

        print(f"Test finished. Best minimum found: {current_best:.4f}")
        print(f"Total evaluations: {total_evals}")
        print(f"Total time: {time.time() - start_time:.2f}s")
        return num_evaluations, best_results_over_time

    # --- Standard logic for optimizers requiring a backend model ---
    # A new test client is created for each request to ensure statelessness.
    param_names = [f'x{i+1}' for i in range(dims)]
    
    # Handle different bounds formats (single tuple or list of tuples).
    param_mins = bounds[0] if isinstance(bounds[0], list) else [bounds[0]] * dims
    param_maxes = bounds[1] if isinstance(bounds[1], list) else [bounds[1]] * dims

    settings: Dict[str, Any] = {
        "base_estimator": optimizer_type,
        "acquisition_function": "LCB",
        "acq_optimizer": "auto",
        "acq_func_kwargs": {"kappa": 1.96},
        "num_params": dims,
        "param_names": param_names,
        "param_mins": param_mins,
        "param_maxes": param_maxes,
        "num_init_points": NUM_INIT_POINTS,
        "batch_size": BATCH_SIZE,
        "random_state": 42
    }

    # Apply any custom settings for this specific run.
    if override_settings:
        settings.update(override_settings)

    # 1. Initialize the optimization process.
    try:
        app = flask_app.test_client()
        response = app.post(
            '/init-optimization',
            json={"settings": settings},
            headers={"X-User-Email": "test@gmail.com"}
        )
        response_data = response.get_json()
        if response.status_code != 200:
            raise requests.RequestException(f"Error: {response_data.get('message')}")
        points_to_evaluate = response_data['data']
    except Exception as e:
        print(f"Error initializing optimization: {e}")
        return [], []

    all_evaluated_points: List[Dict[str, Any]] = []
    best_results_over_time: List[float] = []
    num_evaluations: List[int] = []
    current_best = float('inf')
    total_evals = 0

    # 2. Evaluate the initial set of points.
    print(f"Iteration 0/{NUM_ITERATIONS}... (Initial points: {len(points_to_evaluate)})")
    evaluated_this_iteration: List[Dict[str, Any]] = []
    for point in points_to_evaluate:
        params = np.array([point[name] for name in param_names])
        true_val = func(params)
        noisy_val = true_val + np.random.normal(0, NOISE_LEVEL)
        point['objective'] = noisy_val
        evaluated_this_iteration.append(point)
        
        total_evals += 1
        
        if true_val < current_best:
            current_best = true_val
        
        num_evaluations.append(total_evals)
        best_results_over_time.append(current_best)
    
    all_evaluated_points.extend(evaluated_this_iteration)

    # 3. Run the main optimization loop.
    for i in range(NUM_ITERATIONS):
        try:
            # Create a new client for each request to maintain statelessness.
            app = flask_app.test_client()
            response = app.post(
                '/continue-optimization',
                json={"settings": settings, "existing_data": all_evaluated_points},
                headers={"X-User-Email": "test@gmail.com"}
            )
            response_data = response.get_json()
            print(f"Response data: {response_data}")
            if response.status_code != 200:
                raise requests.RequestException(f"Error: {response_data.get('message')}")
            points_to_evaluate = response_data['data']
        except Exception as e:
            print(f"Error during continue-optimization: {e}")
            break
        
        print(f"Iteration {i+1}/{NUM_ITERATIONS}... ({len(points_to_evaluate)} points)")

        # Evaluate the points suggested by the optimizer.
        evaluated_this_iteration = []
        for point in points_to_evaluate:
            params = np.array([point[name] for name in param_names])
            true_val = func(params)
            noisy_val = true_val + np.random.normal(0, NOISE_LEVEL)
            point['objective'] = noisy_val
            print('POINT:', point)
            evaluated_this_iteration.append(point)
            
            total_evals += 1
            
            if true_val < current_best:
                current_best = true_val
            print('CURRENT BEST:', current_best )
            
            # Track the best result after each individual evaluation.
            num_evaluations.append(total_evals)
            best_results_over_time.append(current_best)
        
        all_evaluated_points.extend(evaluated_this_iteration)

    print(f"Test finished. Best minimum found: {current_best:.4f}")
    print(f"Total evaluations: {total_evals}")
    print(f"Total time: {time.time() - start_time:.2f}s")

    return num_evaluations, best_results_over_time

def compare_optimizers(
    func: Callable[[np.ndarray], float],
    name: str,
    dims: int,
    bounds: Tuple[float, float],
    true_minimum: float,
    optimizers: Optional[List[str]] = None
) -> None:
    """
    Compares multiple optimizer types on the same function and plots the results.

    This function runs each optimizer for a specified number of runs (`NUM_RUNS`)
    and averages their performance to produce a convergence plot. The 'gp_hedge'
    acquisition function is used by default for all model-based optimizers.
    """
    if optimizers is None:
        optimizers = OPTIMIZERS
    
    plt.figure(figsize=(16, 10))
    
    # Store min/max values for adjusting plot limits later.
    plot_min_val = float('inf')
    plot_max_val = float('-inf')

    # Standard settings for regressor comparison: use gp_hedge.
    regressor_settings: Dict[str, Any] = {
        "acquisition_function": "gp_hedge",
        "acq_optimizer": "auto",
        "acq_func_kwargs": {}
    }

    for optimizer_type in optimizers:
        all_runs_results: List[List[float]] = []
        max_evals = 0
        
        print(f"\nRunning {optimizer_type} for {NUM_RUNS} runs...")
        for i in range(NUM_RUNS):
            print(f"  Run {i+1}/{NUM_RUNS}")
            # Enforce 'gp_hedge' acquisition function via override settings.
            num_evals, best_results = run_test(
                func, name, dims, bounds, true_minimum, 
                optimizer_type,
                override_settings=regressor_settings
            )
            if num_evals:
                all_runs_results.append(best_results)
                max_evals = max(max_evals, num_evals[-1])

        if not all_runs_results:
            continue

        # Interpolate results to a common evaluation axis for averaging.
        eval_axis = np.arange(1, max_evals + 1)
        interpolated_runs = []
        for run_results in all_runs_results:
            run_evals = np.arange(1, len(run_results) + 1)
            # Use a step-wise function for interpolation.
            interp_func = np.interp(eval_axis, run_evals, run_results, right=run_results[-1])
            interpolated_runs.append(interp_func)

        # Average the results across all runs.
        avg_results = np.mean(interpolated_runs, axis=0)
        
        plt.plot(eval_axis, avg_results, marker='o', label=f'{optimizer_type}', alpha=0.7, markersize=3)
        plot_min_val = min(plot_min_val, np.min(avg_results))
        plot_max_val = max(plot_max_val, np.max(avg_results))

    plt.xlabel('Number of Objective Function Evaluations', fontsize=12)
    plt.ylabel('Average Best Objective Value Found', fontsize=12)
    plt.title(f'Regressor Comparison (gp_hedge): {name} Function (Avg. over {NUM_RUNS} runs)', fontsize=14)
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    
    # Adjust y-axis scale for better visualization (log scale if appropriate).
    if plot_min_val < float('inf') and all(r > 0 for r in avg_results):
        plt.yscale('log')
        padding = (np.log10(plot_max_val) - np.log10(plot_min_val)) * 0.1 if plot_max_val > 0 and plot_min_val > 0 else 1
        plt.ylim(bottom=10**(np.log10(plot_min_val) - padding), top=10**(np.log10(plot_max_val) + padding))
    else:
        padding = (plot_max_val - plot_min_val) * 0.1 if (plot_max_val - plot_min_val) > 1e-9 else 0.1
        plt.ylim(plot_min_val - padding, plot_max_val + padding)

    output_dir = "test_results"
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f'{name.lower().replace(" ", "_")}_regressor_comparison.png')
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"\nRegressor comparison plot saved to {filename}\n")
    plt.close()


def compare_acquisition_functions(
    func: Callable[[np.ndarray], float],
    name: str,
    dims: int,
    bounds: Tuple[float, float],
    true_minimum: float
) -> None:
    """
    Compares different acquisition functions for the GP optimizer.

    This function tests a predefined set of acquisition functions and their
    configurations to see how they affect the optimization performance on a
    given problem.
    """
    
    acq_configs: Dict[str, Dict[str, Any]] = {
        "EI (sampling)": {"acquisition_function": "EI", "acq_optimizer": "sampling", "acq_func_kwargs": {}},
        "EI (lbfgs)": {"acquisition_function": "EI", "acq_optimizer": "lbfgs", "acq_func_kwargs": {}},
        "PI (sampling)": {"acquisition_function": "PI", "acq_optimizer": "sampling", "acq_func_kwargs": {}},
        "PI (lbfgs)": {"acquisition_function": "PI", "acq_optimizer": "lbfgs", "acq_func_kwargs": {}},
        "LCB (k=0.5)": {"acquisition_function": "LCB", "acq_optimizer": "lbfgs", "acq_func_kwargs": {"kappa": 0.5}},
        "LCB (k=4.0)": {"acquisition_function": "LCB", "acq_optimizer": "lbfgs", "acq_func_kwargs": {"kappa": 1.0}},
        "LCB (k=1.96)": {"acquisition_function": "LCB", "acq_optimizer": "lbfgs", "acq_func_kwargs": {"kappa": 1.96}},
        "gp_hedge": {"acquisition_function": "gp_hedge", "acq_optimizer": "auto", "acq_func_kwargs": {}},
    }

    plt.figure(figsize=(16, 10))
    plot_min_val = float('inf')
    plot_max_val = float('-inf')

    for label, config in acq_configs.items():
        all_runs_results: List[List[float]] = []
        max_evals = 0
        
        print(f"\nRunning GP with {label} for {NUM_RUNS} runs...")
        for i in range(NUM_RUNS):
            print(f"  Run {i+1}/{NUM_RUNS}")
            
            # Pass the specific acquisition function config as an override.
            num_evals, best_results = run_test(
                func, name, dims, bounds, true_minimum, 
                optimizer_type="SKOPT-GP",
                override_settings=config
            )
            
            if num_evals:
                all_runs_results.append(best_results)
                max_evals = max(max_evals, num_evals[-1])

        if not all_runs_results:
            continue

        # Interpolate and average results across runs.
        eval_axis = np.arange(1, max_evals + 1)
        interpolated_runs = []
        for run_results in all_runs_results:
            run_evals = np.arange(1, len(run_results) + 1)
            interp_func = np.interp(eval_axis, run_evals, run_results, right=run_results[-1])
            interpolated_runs.append(interp_func)

        avg_results = np.mean(interpolated_runs, axis=0)
        
        plt.plot(eval_axis, avg_results, marker='o', label=label, alpha=0.7, markersize=3)
        plot_min_val = min(plot_min_val, np.min(avg_results))
        plot_max_val = max(plot_max_val, np.max(avg_results))

    plt.xlabel('Number of Objective Function Evaluations', fontsize=12)
    plt.ylabel('Average Best Objective Value Found', fontsize=12)
    plt.title(f'Acquisition Function Comparison: {name} Function (Avg. over {NUM_RUNS} runs)', fontsize=14)
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    
    # Adjust y-axis scale for better visualization.
    if plot_min_val > 0:
        plt.yscale('log')
        padding = (np.log10(plot_max_val) - np.log10(plot_min_val)) * 0.1 if plot_max_val > 0 else 1
        plt.ylim(bottom=10**(np.log10(plot_min_val) - padding), top=10**(np.log10(plot_max_val) + padding))
    else:
        padding = (plot_max_val - plot_min_val) * 0.1 if (plot_max_val - plot_min_val) > 1e-9 else 0.1
        plt.ylim(plot_min_val - padding, plot_max_val + padding)
    
    output_dir = "test_results"
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f'{name.lower().replace(" ", "_")}_acq_func_comparison.png')
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"\nAcquisition function comparison plot saved to {filename}\n")
    plt.close()


if __name__ == "__main__":
    clear_existing_plots()
    
    # Define the suite of benchmark tests to be executed.
    tests: List[Dict[str, Any]] = [
       {"func": sphere, "name": "Sphere", "dims": N_DIMS, "bounds": (-5, 5), "min": 0.0},
       {"func": rosenbrock, "name": "Rosenbrock", "dims": N_DIMS, "bounds": (-3, 3), "min": 0.0},
       {"func": ackley, "name": "Ackley", "dims": N_DIMS, "bounds": (-2, 2), "min": 0.0},
       {"func": linear, "name": "Linear", "dims": N_DIMS, "bounds": (-5, 5), "min": -20.0}, # Min depends on dims and bounds
       {"func": rastrigin, "name": "Rastrigin", "dims": N_DIMS, "bounds": (-5.12, 5.12), "min": 0.0},
       {"func": griewank, "name": "Griewank", "dims": N_DIMS, "bounds": (-30, 30), "min": 0.0},
       {"func": schwefel, "name": "Schwefel", "dims": N_DIMS, "bounds": (-500, 500), "min": 0.0},
       {"func": polynomial_3, "name": "3rd Order Poly", "dims": N_DIMS, "bounds": (-10, 10), "min": -1}, # True minimum is unknown
    ]

    for test in tests:
        # 1. Compare different surrogate models (regressors).
        compare_optimizers(
            func=test['func'],
            name=test['name'],
            dims=test['dims'],
            bounds=test['bounds'],
            true_minimum=test['min'],
            optimizers=OPTIMIZERS
        )
        
        # 2. Compare different acquisition functions using the GP model.
        compare_acquisition_functions(
            func=test['func'],
            name=test['name'],
            dims=test['dims'],
            bounds=test['bounds'],
            true_minimum=test['min']
        )
