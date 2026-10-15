"""
rag/agent.py
------------
A LangGraph ReAct agent that uses the GraphRAGRetriever as a tool
to answer complex queries using Chain of Thought, augmented with a 
Mixture of Experts (MoE) Verification step to prevent hallucinations.
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Fix Windows console encoding issues for Unicode characters
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from rag.retriever import GraphRAGRetriever

# Load environment variables (e.g., GOOGLE_API_KEY)
load_dotenv()

_retriever = None

def _get_retriever():
    global _retriever
    if _retriever is None:
        print("Initializing GraphRAG Retriever...")
        _retriever = GraphRAGRetriever()
    return _retriever

@tool
def search_knowledge_base(query: str) -> str:
    """Useful for when you need to answer questions about MetaKGP, IIT Kharagpur, halls, courses, and related entities. 
    Input should be a specific search query. You can call this tool multiple times to gather all necessary information."""
    return _get_retriever().search_for_agent(query, top_k=10)

class MoEVerification(BaseModel):
    source_matcher_passed: bool = Field(description="Does the text in the retrieved chunk actually support this claim? True if yes.")
    hallucination_hunter_passed: bool = Field(description="Is the bot inventing details not present in the scraped context? True if NO hallucinations exist.")
    logic_expert_passed: bool = Field(description="Does the conclusion follow from the premises? True if logically sound.")
    feedback: str = Field(description="If any verification failed, provide detailed feedback on what needs to be fixed. If all passed, say 'Looks good'.")
    is_valid: bool = Field(description="True if all three experts passed.")

def run_moe_verification(llm, query: str, context: str, draft_answer: str) -> MoEVerification:
    verifier_llm = llm.with_structured_output(MoEVerification)
    prompt = f"""
    You are a panel of three strict expert verifiers evaluating an AI's draft answer to a user query.
    
    User Query: {query}
    
    Retrieved Context:
    {context}
    
    Draft Answer:
    {draft_answer}
    
    Evaluate the draft answer strictly based on the retrieved context using the following experts:
    1. Source Matcher: "Does the text in the retrieved chunk actually support this claim?"
    2. Hallucination Hunter: "Is the bot inventing details not present in the scraped context?"
    3. Logic Expert: "Does the conclusion follow from the premises?"
    """
    return verifier_llm.invoke(prompt)

def get_llm():
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY or GEMINI_API_KEY environment variable not found. Please add it to your .env file.")
        exit(1)

    model_name = os.getenv("LLM_MODEL", "gemini-3.8-flash")

    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.0,
        google_api_key=api_key
    )

def create_agent(llm):
    tools = [search_knowledge_base]
    agent = create_react_agent(
        llm, 
        tools=tools, 
        prompt="Answer the user's questions as best you can. You can use the search_knowledge_base tool to find information."
    )
    return agent

if __name__ == '__main__':
    print("Welcome to the GraphRAG Conversational Agent!")
    print("Type 'exit' or 'quit' to end the session.\n")
    
    llm = get_llm()
    agent = create_agent(llm)
    
    chat_history = []
    max_retries = 3
    
    while True:
        try:
            user_input = input("You: ")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break
            
        if user_input.strip().lower() in ['exit', 'quit']:
            print("Goodbye!")
            break
            
        if not user_input.strip():
            continue
            
        # Prepare the current messages with chat history + the new query
        current_messages = list(chat_history)
        current_messages.append(("user", user_input))
        
        for attempt in range(max_retries):
            print(f"==================================================")
            print(f" [Agent Attempt {attempt + 1} / {max_retries}]")
            print(f"==================================================")
            
            try:
                inputs = {"messages": current_messages}
                # We invoke the agent to get the full final state
                final_state = agent.invoke(inputs)
                
                # Print the new messages from this run
                new_msgs = final_state["messages"][len(current_messages):]
                for msg in new_msgs:
                    msg.pretty_print()
                    
                final_ai_msg = final_state["messages"][-1].content
                
                # Extract the context from ToolMessages
                contexts = []
                for msg in final_state["messages"]:
                    if getattr(msg, "name", "") == "search_knowledge_base":
                        contexts.append(str(msg.content))
                        
                combined_context = "\n\n".join(contexts)
                if not combined_context:
                    combined_context = "No context retrieved from knowledge base."
                    
                print("\n[MoE] Running Verification Experts on Draft Answer...")
                verification = run_moe_verification(llm, user_input, combined_context, final_ai_msg)
                
                print(f"  - Source Matcher Passed: {verification.source_matcher_passed}")
                print(f"  - Hallucination Hunter Passed: {verification.hallucination_hunter_passed}")
                print(f"  - Logic Expert Passed: {verification.logic_expert_passed}")
                
                if verification.is_valid:
                    print("\n✅ [MoE] VERIFICATION PASSED! Final Answer Approved.")
                    
                    # Store the verified answer in the persistent chat history
                    chat_history.append(("user", user_input))
                    chat_history.append(("assistant", final_ai_msg))
                    break
                else:
                    print(f"\n❌ [MoE] VERIFICATION FAILED. Feedback: {verification.feedback}")
                    if attempt < max_retries - 1:
                        print("\n🔄 Triggering self-correction retry...")
                        current_messages = final_state["messages"]
                        current_messages.append(("user", f"Your previous answer failed verification. Here is the feedback from the experts:\n{verification.feedback}\nPlease revise your answer to address these issues. DO NOT hallucinate. Use the tool again if necessary."))
                    else:
                        print("\n⚠️ Maximum retries reached. Proceeding with unverified answer.")
                        chat_history.append(("user", user_input))
                        chat_history.append(("assistant", final_ai_msg))
                
            except Exception as e:
                print(f"\n[Agent Error]: {e}")
                break
