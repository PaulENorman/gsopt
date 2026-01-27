---
layout: default
title: Benchmark Results
nav_order: 4
---

# Benchmark Test Results

The plots below show the performance of different optimizer configurations on standard benchmark functions. These tests were run using the `evaluate.py` script in the repository.

## Test Configuration

The results were generated with the following settings to simulate a realistic use case:
*   **Dimensions:** 5 (`N_DIMS = 5`)
*   **Noise:** A small amount of Gaussian noise (`NOISE_LEVEL = 0.01`) was added to the objective function to simulate real-world measurement error.
*   **Initial Points:** 20 randomly sampled points were evaluated before starting model-based optimization (`NUM_INIT_POINTS = N_DIMS * 4`).
*   **Batch Size:** 5 new points were requested from the optimizer at each iteration (`BATCH_SIZE = N_DIMS`).
*   **Averaging:** Each test was run 5 times (`NUM_RUNS = 5`), and the results were averaged to ensure the conclusions are robust.

## Regressor Performance

The following plot compares the performance of different surrogate models (regressors) on the Rosenbrock function, a classic difficult non-convex problem. All optimizers used the `gp_hedge` acquisition function. The `SKOPT-GP` (Gaussian Process) finds the lowest minimum at the end of the two hundred iterations, although it underperforms early on.
<img src="{{ '/images/test_results/rosenbrock_regressor_comparison.png' | relative_url }}" alt="Rosenbrock Regressor Comparison" width="800">

## Acquisition Function Performance

This plot compares different acquisition functions for the `SKOPT-GP` optimizer on the Ackley function, which has many local minima. The `gp_hedge` strategy shows strong, consistent performance, while the LCB with both high and low kappas also perform well.

<img src="{{ '/images/test_results/ackley_acq_func_comparison.png' | relative_url }}" alt="Ackley Acquisition Function Comparison" width="800">

For recommended starting settings, GP is recommended as an acquisition function, with gp_hedge as the acquisition function. If your problem probably only has one local minimum and you are looking find it quickly, LCB with a k = 0.5 is a good choice.