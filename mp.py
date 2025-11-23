from memory_profiler import profile
import sys

@profile
def test_imports():
    """Test memory usage of imports"""
    import pandas as pd
    import numpy as np
    from skopt import Optimizer
    from skopt.space import Real
    import jwt
    from jwt import PyJWKClient
    print("All imports complete")

@profile
def test_optimizer_creation():
    """Test memory usage of optimizer creation"""
    from skopt import Optimizer
    from skopt.space import Real
    
    space = [Real(-10, 10, name=f"param{i}") for i in range(10)]
    optimizer = Optimizer(space, base_estimator='GP', acq_func='EI', n_initial_points=5)
    points = optimizer.ask(n_points=20)
    print(f"Generated {len(points)} points")

if __name__ == '__main__':
    print("Testing imports...")
    test_imports()
    print("\nTesting optimizer creation...")
    test_optimizer_creation()