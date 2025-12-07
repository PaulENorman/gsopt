---
layout: default
title: Home
nav_order: 1
---

# gs-opt: Human-in-the-loop Batched Optimization

## Overview

Optimizing real-world engineering problems is often challenging. When the function you want to optimize is expensive, noisy, and lacks a simple mathematical form (aka "black box", with no information on the derivatives of the function), many traditional methods fall short. `gs-opt` is designed for this type of probem by implementing a **human-in-the-loop** batched submission optimization workflow for noisy black box problems. The optimization process is orchestrated through a Google Spread Sheet, so it easy to use for engineers.

The basic workflow is:
1.  The optimizer suggests a batch of initial points based on the parameter settings.
2.  You, the user, perform the experiments and copy the results in a Google Spread Sheet.
3.  Ask the optimizer for new promising poitns to run, and use the analysis plots to keep track of the optimization. Repeat as necesarry.

The Google Sheet acts as the central hub, storing all experimental data, providing basic analysis plots, and serving as the user interface for interacting with the optimization engine. All the optimization code and macros are in this repo: https://github.com/PaulENorman/gsopt.

## Google Sheet Usage

*(This section will be populated with screenshots demonstrating the usage of the Google Sheet.)*

## The Optimizer

The optimization is powered by `scikit-optimize`, a robust and popular library for sequential model-based optimization. `gs-opt` uses its Bayesian optimizer to intelligently navigate the search space. You can find more details about the library on the [`scikit-optimize` website](https://scikit-optimize.github.io/stable/).

### Bayesian Optimization with `scikit-optimize`

Bayesian optimization is an efficient strategy for finding the maximum or minimum of black-box functions. It works by building a probabilistic model of the objective function (the "surrogate model") and using that model to select the most promising points to evaluate next. This approach is  effective for problems where each function evaluation is costly (e.g., time-consuming experiments or expensive computations).

In `gs-opt`, you can configure the `scikit-optimize` backend by choosing the surrogate model (regressor) and the acquisition function.

*   **Regressor**: This is the probabilistic model used to approximate the objective function. While Gaussian Processes are the most common choice for Bayesian optimization, `scikit-optimize` also supports other tree-based models which can be effective.
    *   `GP` (Gaussian Process): A powerful and common choice for Bayesian optimization due to its ability to provide smooth interpolations and reliable uncertainty estimates for its predictions. This is the recommended default.
    *   `RF` (Random Forest): An ensemble of decision trees. It can capture complex, non-linear relationships but provides a less smooth approximation of the objective function.
    *   `ET` (Extra Trees): Similar to a Random Forest, but with more randomness in how splits in the trees are chosen. This can sometimes help in exploring the search space more effectively.
    *   `GBRT` (Gradient Boosted Regression Trees): An ensemble method that builds trees sequentially, where each new tree attempts to correct the errors of the previous ones. It can be a very powerful model but is sometimes prone to overfitting.

*   **Acquisition Function**: This function guides the search for the optimum. It uses the surrogate model's predictions and uncertainty estimates to determine the "utility" of evaluating any given point. It balances **exploration** (sampling in areas of high uncertainty to improve the model) and **exploitation** (sampling in areas likely to yield a good objective value). The main options available are:
    *   `gp_hedge`: A dynamic strategy that adaptively chooses between several acquisition functions at each iteration.
    *   `LCB` (Lower Confidence Bound): Explicitly balances exploration and exploitation using a parameter `kappa`. A low `kappa` favors exploitation, while a high `kappa` encourages more exploration.
    *   `EI` (Expected Improvement): A classic choice that focuses on the expected amount of improvement over the current best-found value.
    *   `PI` (Probability of Improvement): Similar to EI, but focuses only on the probability of improving over the current best, rather than the magnitude.

### Pros and Cons

**Pros:**
*   **Sample Efficiency:** Bayesian optimization is designed to find good solutions in a minimal number of function evaluations, making it ideal for expensive problems.
*   **Flexibility:** `scikit-optimize` provides robust and well-tested implementations of various models and acquisition functions.
*   **Handles Noise:** The probabilistic nature of a Gaussian Process surrogate model naturally handles noisy objective functions.

**Cons:**
*   **"Curse of Dimensionality":** Performance can degrade as the number of parameters in the search space increases. Always try to minimize the number of dimensions in your optimization.
*   **Computational Cost:** The cost of fitting the surrogate model grows with the number of observations. For this project, this cost is generally negligible compared to the cost of evaluating the objective function itself.

### Recommendations and Examples

Based on our testing, we have the following recommendations for starting your optimization:

*   **General Purpose:** For a robust, all-around strategy, we recommend using a **Gaussian Process** regressor (`GP`) with the **`gp_hedge`** acquisition function. This method dynamically selects the best acquisition function at each step and generally performs well across a variety of problems.

*   **More Exploitative:** If you believe you are close to an optimum and want to focus on refining the solution, we recommend using **`LCB`** (Lower Confidence Bound) with a small **`kappa` (e.g., 0.5)**. This encourages the optimizer to sample in regions it already knows are good.

*   **More Explorative:** If the optimizer seems stuck in a local minimum, or you want to search the parameter space more broadly, we recommend using **`LCB`** with a large **`kappa` (e.g., 4.0 or higher)**. This pushes the optimizer to explore uncertain regions.

#### Benchmark Test Results

The plots below show the performance of different optimizer configurations on standard benchmark functions. These tests were run using the `evaluate.py` script in the repository.

##### Test Configuration

The results were generated with the following settings to simulate a realistic use case:
*   **Dimensions:** 5 (`N_DIMS = 5`)
*   **Noise:** A small amount of Gaussian noise (`NOISE_LEVEL = 0.01`) was added to the objective function to simulate real-world measurement error.
*   **Initial Points:** 20 randomly sampled points were evaluated before starting model-based optimization (`NUM_INIT_POINTS = N_DIMS * 4`).
*   **Batch Size:** 5 new points were requested from the optimizer at each iteration (`BATCH_SIZE = N_DIMS`).
*   **Averaging:** Each test was run 5 times (`NUM_RUNS = 5`), and the results were averaged to ensure the conclusions are robust.

##### Regressor Performance

The following plot compares the performance of different surrogate models (regressors) on the Rosenbrock function, a classic difficult non-convex problem. All optimizers used the `gp_hedge` acquisition function. The `SKOPT-GP` (Gaussian Process) model consistently finds a better solution faster than the tree-based methods.

![Rosenbrock Regressor Comparison]({{ '/test_results/rosenbrock_regressor_comparison.png' | relative_url }})

##### Acquisition Function Performance

This plot compares different acquisition functions for the `SKOPT-GP` optimizer on the Ackley function, which has many local minima. The `gp_hedge` strategy shows strong, consistent performance. `LCB` with a high kappa (`k=4.0`) is also effective at exploring, while `LCB` with a low kappa (`k=0.5`) exploits more and converges slower on this particular problem.

![Ackley Acquisition Function Comparison]({{ '/test_results/ackley_acq_func_comparison.png' | relative_url }})
