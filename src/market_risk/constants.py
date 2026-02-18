"""Market risk constants."""

# Standard normal distribution z-scores
Z_SCORES: dict[float, float] = {
    0.90: 1.282,
    0.95: 1.645,
    0.99: 2.326,
    0.995: 2.576,
}

# CVaR multipliers (for normal distribution)
CVAR_MULTIPLIERS: dict[float, float] = {
    0.95: 2.063,
    0.99: 2.665,
}
