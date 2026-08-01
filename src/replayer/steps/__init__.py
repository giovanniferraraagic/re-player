"""Model-backed workflow steps.

Each module here owns exactly one LLM-backed executor. Keeping them separate
from the graph makes it obvious which steps can spend tokens.
"""
