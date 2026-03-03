import sys
from pathlib import Path
from app.core.logger_utils import get_logger
from app.core.rag.retriever import VectorRetriever

# To mimic using multiple Python modules, such as 'core' and 'feature_pipeline',
# we will add the './src' directory to the PYTHONPATH. This is not intended for
# production use cases but for development and educational purposes.
ROOT_DIR = str(Path(__file__).parent)
sys.path.append(ROOT_DIR)


logger = get_logger(__name__)

if __name__ == "__main__":
    query = """
Hello I am Paul Iusztin.
        
Could you draft an article paragraph discussing RAG? 
I'm particularly interested in how to design a RAG system.
"""

    retriever = VectorRetriever(query=query)
    hits = retriever.retrieve_top_k(k=6, to_expand_to_n_queries=5)
    reranked_hits = retriever.rerank(hits=hits, keep_top_k=5)

    logger.info("====== RETRIEVED DOCUMENTS ======")
    for rank, hit in enumerate(reranked_hits):
        logger.info(f"Rank = {rank} : {hit}")
