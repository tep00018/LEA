# File: verify_rag_content.py
"""
Verify RAG vector store content and compare chat vs quiz retrieval methods
Run: python data_foundation/verify_rag_content.py [COURSE]   (default: DEFAULT_COURSE, DEMO101)
"""

import asyncio
import sys
from pathlib import Path
import json

# Add the repository root to the path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.core.config import DEFAULT_COURSE
from src.mcp.tools.rag_retrieval_tool import RAGRetrievalTool
from simulation.lea_real_integration2 import RealLEASystemConnector


def first_go(course: str) -> dict:
    """First granular objective in the course's KC model; the test queries below are built from it."""
    path = Path(__file__).resolve().parent.parent / "data" / "kc_models" / course / f"kc_model_{course}.json"
    try:
        model = json.loads(path.read_text(encoding="utf-8"))
        for week in model["week_navigation"].values():
            for lo in week.get("learning_objectives", []):
                for go in lo.get("granular_objectives", []):
                    return go
    except (OSError, ValueError, KeyError):
        pass
    return {"go_id": "GO_01_01_001", "skill_name": "course introduction", "description": "Test GO"}

async def verify_rag_content(course: str = DEFAULT_COURSE):
    """Directly verify what's in the RAG vector store"""
    go = first_go(course)
    
    print("="*70)
    print("RAG VECTOR STORE CONTENT VERIFICATION")
    print("="*70)
    
    # Initialize RAG tool directly
    rag_tool = RAGRetrievalTool()
    
    print(f"\n📚 Available courses: {list(rag_tool.course_collections.keys())}")
    
    # Test 1: Direct MCP-style query (like chat mode uses)
    print("\n" + "="*60)
    print("TEST 1: Chat-Style Query (What Works)")
    print("="*60)
    
    chat_query = f"What is {go['skill_name']}?"
    print(f"\nQuery: '{chat_query}'")
    
    chat_result = await rag_tool.execute({
        "query": chat_query,
        "course": course,
        "max_results": 3,
        "use_reranking": True
    })
    
    print(f"Success: {chat_result.get('success', False)}")
    print(f"Number of results: {len(chat_result.get('results', []))}")
    
    # Detailed inspection of first result
    if chat_result.get('results'):
        first_result = chat_result['results'][0]
        print(f"\nFirst Result Analysis:")
        print(f"  Type: {type(first_result)}")
        
        if isinstance(first_result, dict):
            print(f"  Keys: {list(first_result.keys())}")
            
            # Try all possible content fields
            content_fields = ['content', 'text', 'document', 'page_content', 'chunk_text']
            for field in content_fields:
                if field in first_result:
                    content = first_result[field]
                    if content and str(content).strip() != "metadata":
                        print(f"  ✅ Found real content in '{field}':")
                        print(f"     Preview: {str(content)[:200]}...")
                        break
            else:
                # Check the 'content' field specifically
                content = first_result.get('content', '')
                print(f"  ❌ Content field: '{str(content)[:100]}'")
    
    # Test 2: Quiz-style query (GO-specific)
    print("\n" + "="*60)
    print("TEST 2: Quiz-Style Query (What Fails)")
    print("="*60)
    
    quiz_query = f"{go['go_id']} {go['skill_name']}"
    print(f"\nQuery: '{quiz_query}'")
    
    quiz_result = await rag_tool.execute({
        "query": quiz_query,
        "course": course,
        "max_results": 3,
        "use_reranking": False  # Quiz doesn't use reranking
    })
    
    print(f"Success: {quiz_result.get('success', False)}")
    print(f"Number of results: {len(quiz_result.get('results', []))}")
    
    if quiz_result.get('results'):
        first_result = quiz_result['results'][0]
        content = first_result.get('content', '') if isinstance(first_result, dict) else str(first_result)
        print(f"Content preview: '{str(content)[:200]}'")
    
    # Test 3: Direct collection access (bypass MCP)
    print("\n" + "="*60)
    print("TEST 3: Direct ChromaDB Access")
    print("="*60)
    
    try:
        # Access the underlying ChromaDB collection
        
        if hasattr(rag_tool, 'course_collections'):
            course_entry = rag_tool.course_collections.get(course)

            if course_entry and hasattr(course_entry, '_collection'):
                chroma_collection = course_entry._collection

                print(f"\n📦 Raw ChromaDB documents (first 5):")
                for i, doc in enumerate(raw_results['documents'][:5]):
                    print(f"\nDocument {i+1}:")
                    print(f"  Content: {doc[:200] if doc else 'EMPTY'}...")
                    print(f"  Length: {len(doc) if doc else 0} chars")
                    
                    # Check if it's just metadata
                    if doc and doc.strip().startswith('metadata'):
                        print(f"  ⚠️ WARNING: This is a metadata placeholder!")
                    elif doc and len(doc) > 50:
                        print(f"  ✅ This appears to be real content")
                    else:
                        print(f"  ❌ Content is empty or too short")
                
                # Count metadata vs real content
                metadata_count = sum(1 for doc in raw_results['documents'] 
                                   if doc and doc.strip().startswith('metadata'))
                real_count = sum(1 for doc in raw_results['documents'] 
                               if doc and len(doc) > 50 and not doc.strip().startswith('metadata'))
                
                print(f"\n📊 Content Analysis:")
                print(f"  Metadata placeholders: {metadata_count}/{len(raw_results['documents'])}")
                print(f"  Real content: {real_count}/{len(raw_results['documents'])}")
                
    except Exception as e:
        print(f"❌ Could not access ChromaDB directly: {e}")
    
    # Test 4: Compare retrieval methods
    print("\n" + "="*60)
    print("TEST 4: Why Chat Works but Quiz Doesn't")
    print("="*60)
    
    # Initialize LEA connector to test both modes
    connector = RealLEASystemConnector(course=course)
    
    # Test chat mode retrieval
    print("\n🗨️ Chat Mode Retrieval:")
    chat_result = await connector.process_chat_interaction(
        f"Explain {go['skill_name']}",
        course=course,
        week=1
    )
    print(f"  RAG Retrieved: {chat_result['rag_retrieved']}")
    print(f"  Answer preview: {chat_result.get('generated_answer', '')[:100]}...")
    
    # Look at how quiz gets content
    print("\n📝 Quiz Mode RAG Check:")
    print("  Checking SimpleQuizSystem._get_rag_content() method...")
    
    # The issue might be in how quiz extracts content
    test_go = {
        'go_id': go['go_id'],
        'skill_name': go['skill_name'],
        'description': go.get('description', 'Test GO')
    }
    
    # Simulate what quiz does
    query = f"{test_go['skill_name']} {test_go['description']}"
    quiz_rag_result = await rag_tool.execute({
        "query": query,
        "course": course,
        "max_results": 5,
        "use_reranking": False
    })
    
    print(f"  Query: '{query[:50]}...'")
    print(f"  Results returned: {len(quiz_rag_result.get('results', []))}")
    
    # Check content extraction
    if quiz_rag_result.get('results'):
        for i, result in enumerate(quiz_rag_result['results'][:3]):
            if isinstance(result, dict):
                content = result.get('content', '')
                # This is likely where the issue is - content field has "metadata"
                if str(content).strip().startswith('metadata'):
                    print(f"  Result {i+1}: ❌ Metadata placeholder")
                else:
                    print(f"  Result {i+1}: ✅ Real content ({len(str(content))} chars)")
    
    print("\n" + "="*70)
    print("DIAGNOSIS COMPLETE")
    print("="*70)
    
    print("\n🔍 Key Findings:")
    print("1. If chat works: RAG can retrieve real content")
    print("2. If quiz fails: Content extraction or query format issue")
    print("3. If all documents are 'metadata': Vector store needs re-population")
    print("4. If mixed content: Query matching might be the issue")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Verify the RAG vector store for a course")
    parser.add_argument("course", nargs="?", default=DEFAULT_COURSE, help="course code (default: %(default)s)")
    cli = parser.parse_args()
    print("🔍 Starting RAG content verification...\n")
    asyncio.run(verify_rag_content(cli.course))
    asyncio.run(verify_rag_content())