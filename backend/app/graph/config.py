"""Configuration is evaluated at call time for easy VS Code switching."""
import os
from .repository import BoltGraphRepository

def repository_from_env() -> BoltGraphRepository:
    backend = os.getenv('GRAPH_BACKEND', 'memgraph').lower()
    default_uri = 'bolt://memgraph:7687' if backend == 'memgraph' else 'bolt://neo4j:7687'
    return BoltGraphRepository(backend, os.getenv('GRAPH_URI', default_uri),
                               os.getenv('GRAPH_USER', 'neo4j' if backend == 'neo4j' else ''),
                               os.getenv('GRAPH_PASSWORD', ''),
                               os.getenv('GRAPH_DATABASE') or None)
