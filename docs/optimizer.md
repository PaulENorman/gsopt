---
layout: default
title: The Optimizer
nav_order: 2
---

# The Optimizer

The optimization is powered by `scikit-optimize`, a robust and popular library for sequential model-based optimization. `gs-opt` uses its Bayesian optimizer to intelligently navigate the search space. You can find more details about the library on the [`scikit-optimize` website](https://scikit-optimize.github.io/stable/).

## Bayesian Optimization with `scikit-optimize`

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
