---
layout: default
title: Recommendations
nav_order: 3
---

# Recommendations and Examples

## Pros and Cons

**Pros:**
*   **Sample Efficiency:** Bayesian optimization is designed to find good solutions in a minimal number of function evaluations, making it ideal for expensive problems.
*   **Flexibility:** `scikit-optimize` provides robust and well-tested implementations of various models and acquisition functions.
*   **Handles Noise:** The probabilistic nature of a Gaussian Process surrogate model naturally handles noisy objective functions.

**Cons:**
*   **"Curse of Dimensionality":** Performance can degrade as the number of parameters in the search space increases. Always try to minimize the number of dimensions in your optimization.
*   **Computational Cost:** The cost of fitting the surrogate model grows with the number of observations. For this project, this cost is generally negligible compared to the cost of evaluating the objective function itself.

## Recommendations

Based on our testing, we have the following recommendations for starting your optimization:

*   **General Purpose:** For a robust, all-around strategy, we recommend using a **Gaussian Process** regressor (`GP`) with the **`gp_hedge`** acquisition function. This method dynamically selects the best acquisition function at each step and generally performs well across a variety of problems.

*   **More Exploitative:** If you believe you are close to an optimum and want to focus on refining the solution, we recommend using **`LCB`** (Lower Confidence Bound) with a small **`kappa` (e.g., 0.5)**. This encourages the optimizer to sample in regions it already knows are good.

*   **More Explorative:** If the optimizer seems stuck in a local minimum, or you want to search the parameter space more broadly, we recommend using **`LCB`** with a large **`kappa` (e.g., 4.0 or higher)**. This pushes the optimizer to explore uncertain regions.
