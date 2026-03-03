from langgraph.graph import StateGraph, END
from app.core.agent.teaching.state import TeachingState
from app.core.agent.teaching.nodes import (
    parse_document_node,
    syllabus_design_node,
    course_content_design_node,
    guided_learning_node
)

def check_next_step(state: TeachingState):
    """
    Determines whether to stay in guided learning or move to the next module.
    """
    messages = state["messages"]
    last_msg = messages[-1].content.lower() if messages else ""
    
    # Simple heuristic for now: user says "next module" or "finish chapter"
    if "next module" in last_msg or "finish chapter" in last_msg:
        # Check if there are more modules
        current_idx = state.get("current_module_index", 0)
        syllabus = state.get("syllabus", [])
        
        if current_idx + 1 < len(syllabus):
            return "next_module"
        else:
            return "end_course"
            
    return "continue_learning"

def update_module_index(state: TeachingState):
    return {"current_module_index": state.get("current_module_index", 0) + 1}

# Create Graph
workflow = StateGraph(TeachingState)

# Add Nodes
workflow.add_node("parse_document", parse_document_node)
workflow.add_node("syllabus_design", syllabus_design_node)
workflow.add_node("course_content_design", course_content_design_node)
workflow.add_node("guided_learning", guided_learning_node)
workflow.add_node("update_index", update_module_index)

# Set Entry Point
workflow.set_entry_point("parse_document")

# Add Edges
workflow.add_edge("parse_document", "syllabus_design")
workflow.add_edge("syllabus_design", "course_content_design")
workflow.add_edge("course_content_design", "guided_learning")
workflow.add_edge("update_index", "course_content_design")

# Conditional Edges from Guided Learning
workflow.add_conditional_edges(
    "guided_learning",
    check_next_step,
    {
        "continue_learning": END,  # Yield control to user
        "next_module": "update_index",
        "end_course": END
    }
)

# Compile
teaching_graph = workflow.compile()
