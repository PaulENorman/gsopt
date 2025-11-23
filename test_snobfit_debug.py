
import numpy as np
from SQSnobFit import optset, snobfit

def test_snobfit_behavior():
    print("Testing SQSnobFit behavior...")
    
    # Setup basic problem
    # SNOBFIT usually expects bounds as (n_dim, 2) where col 0 is min, col 1 is max.
    # My code in opt_snobfit.py does: np.array([self.param_mins, self.param_maxes])
    # which results in (2, n_dim).
    # Wait!
    # param_mins = [-5, -5]
    # param_maxes = [5, 5]
    # np.array([mins, maxes]) -> shape (2, 2).
    # Row 0 is mins, Row 1 is maxes.
    
    x = np.random.uniform(-5, 5, (10, 2))
    f = np.sum(x**2, axis=1).reshape(-1, 1)
    # Add noise column
    f = np.hstack([f, np.zeros_like(f) + 0.01])
    
    # params = optset(nreq=1) # This failed before
    params = optset()
    # params['nreq'] = 1 # This also fails
    
    print("\n--- Attempt 1: snobfit(x, f, bounds, params) ---")
    try:
        # Try bounds as (n_dim, 2) -> [[-5, 5], [-5, 5]]
        b = np.column_stack(([-5, -5], [5, 5]))
        print(f"Bounds shape: {b.shape}")
        print(f"Bounds:\n{b}")
        
        # Try 4 arguments: x, f, bounds, params
        ret = snobfit(x, f, b, params)
        print("Success with 4 args!")
        print(f"Return type: {type(ret)}")
        print(f"Return length: {len(ret)}")
        if len(ret) == 3:
            req, xbest, fbest = ret
            print("Unpacked 3 values: request, xbest, fbest")
            print(f"Request (first element): {req[0] if len(req)>0 else 'empty'}")
            print(f"xbest: {xbest}")
            print(f"fbest: {fbest}")
    except Exception as e:
        print(f"Failed with 4 args: {e}")

    print("\n--- Attempt 2: snobfit(x, f, bounds, params) with (2, n_dim) bounds ---")
    try:
        # Try bounds as (2, n_dim) -> [[-5, -5], [5, 5]] (Current implementation)
        b = np.array([[-5, -5], [5, 5]])
        print(f"Bounds shape: {b.shape}")
        
        ret = snobfit(x, f, b, params)
        print("Success with (2, n_dim) bounds!")
    except Exception as e:
        print(f"Failed with (2, n_dim) bounds: {e}")


if __name__ == "__main__":
    test_snobfit_behavior()
