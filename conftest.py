"""Root conftest.py - sets environment variables before any imports."""
import os

# Set test environment variables BEFORE any somaai imports
os.environ["SOMAAI_ENV"] = "test"
os.environ["SOMAAI_LLM__BACKEND"] = "mock"
