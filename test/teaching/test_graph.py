import os
import sys
import json
from unittest.mock import MagicMock, patch

# Ensure app is in path
sys.path.append(os.getcwd())

# --- AGGRESSIVE MOCKING START ---
# Mock the entire retriever module to verify no DB connections are attempted
mock_retriever_module = MagicMock()
sys.modules["app.core.rag.retriever"] = mock_retriever_module

# Mock the VectorRetriever class specifically
mock_vector_retriever = MagicMock()
mock_retriever_module.VectorRetriever = mock_vector_retriever
# --- AGGRESSIVE MOCKING END ---

from langchain_core.messages import HumanMessage, AIMessage

# Mock the client
with patch("app.core.agent.call_llm.client") as mock_client:
    # Setup Mock Responses
    def side_effect(prompt, **kwargs):
        # Syllabus Node
        if "expert curriculum designer" in str(prompt):
            return AIMessage(content='[{"title": "Module 1", "summary": "Intro"}, {"title": "Module 2", "summary": "Next"}]')
        
        # Course Content Node
        if "Professor" in str(prompt) or "Training Script" in str(prompt):
            return AIMessage(content="# Module 1 Script\n\nExplain things...")
            
        if "Next module" in str(prompt):
            return AIMessage(content="Okay, moving to the next module.")

        # Guided Learning Node
        return AIMessage(content="Hello! Let's learn about Module 1. Any questions?")

    mock_client.invoke.side_effect = side_effect

    # Now we can safely import the graph code
    # The nodes.py will import 'VectorRetriever' from our mocked module
    from app.core.agent.teaching.graph import teaching_graph
    from app.core.agent.teaching.state import TeachingState
    
    # We might need to patch client in nodes manually if it was already imported (it shouldn't be with this structure, but good to be safe)
    import app.core.agent.teaching.nodes as nodes
    nodes.client = mock_client

    def test_workflow():
        # Create a dummy training doc
        doc_path = "test_training.md"
        with open(doc_path, "w") as f:
            f.write("# Introduction to Banking\n\nBanking is about money...")
            
        print("Created test document.")
        
        # Initialize State
        initial_state = TeachingState(
            messages=[],
            document_path=doc_path,
            syllabus=[],
            user_progress={},
            course_contents={},
            context_docs=[],
            current_module_index=0
        )
        
        print("Invoking graph (Parsing -> Syllabus -> Course Design -> Guided Learning)...")
        result = teaching_graph.invoke(initial_state)
        
        print("Graph execution 1 finished.")
        print("Syllabus:", result.get("syllabus"))
        # Verify Syllabus
        assert len(result.get("syllabus")) == 2
        assert result.get("syllabus")[0]["title"] == "Module 1"
        # Verify Content
        assert "Module 1" in result.get("course_contents")
        # Verify Messages
        assert "Hello!" in result.get("messages")[-1].content
        
        # Simulate User reply "Next Module"
        print("\nSimulating User Input: 'Next Module'...")
        state_next = result
        state_next["messages"].append(HumanMessage(content="Next module please."))
        
        # Run again
        result_2 = teaching_graph.invoke(state_next)
        
        print("Graph execution 2 finished.")
        print("Current Module Index:", result_2.get("current_module_index"))
        
        # Should have incremented
        assert result_2.get("current_module_index") == 1
        
        print("\nSUCCESS: Graph logic verified.")
        
        # Cleanup
        if os.path.exists(doc_path):
            os.remove(doc_path)
            
    if __name__ == "__main__":
        test_workflow()
