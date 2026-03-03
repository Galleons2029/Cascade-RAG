import os


# Configure Graphiti

from graphiti_core import Graphiti

neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

client = Graphiti(
    neo4j_uri,
    neo4j_user,
    neo4j_password,
)
