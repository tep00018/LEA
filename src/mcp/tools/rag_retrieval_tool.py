# src/mcp/tools/rag_retrieval_tool.py
"""
RAG Retrieval Tool for LEA MCP Server
Handles multi-course RAG operations with ChromaDB using per-course directories
"""

import os
import json
import asyncio
import chromadb
import nltk
from typing import Dict, Any, List, Optional
from sentence_transformers import CrossEncoder
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import torch

# Load environment variables if not already loaded
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv might not be available in all environments

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

class RAGRetrievalTool:
    """
    RAG tool that manages multiple course collections using separate ChromaDB instances
    Each course now has its own dedicated ChromaDB directory for better isolation
    """
    
    def __init__(self):
        """Initialize RAG tool with per-course ChromaDB clients"""
        self.tool_name = "rag_retrieval"
        self.description = "Retrieve relevant course content using RAG"
        
        # Base directory for all course databases - this is the main directory reference
        self.base_chroma_dir = "data/chroma_data"
        
        # Ensure base directory exists
        if not os.path.exists(self.base_chroma_dir):
            print(f"DEBUG: Base ChromaDB directory not found: {self.base_chroma_dir}")
            # Try alternative base paths if the default doesn't exist
            alt_base_paths = ["./data/chroma_data", "../data/chroma_data", "chroma_data"]
            for alt_path in alt_base_paths:
                if os.path.exists(alt_path):
                    self.base_chroma_dir = alt_path
                    print(f"DEBUG: Using alternative base ChromaDB path: {alt_path}")
                    break
            else:
                print(f"DEBUG: Creating base ChromaDB directory: {self.base_chroma_dir}")
                os.makedirs(self.base_chroma_dir, exist_ok=True)
        
        print(f"DEBUG: Base ChromaDB directory set to: {self.base_chroma_dir}")
        
        # OpenAI embedding function with robust API key loading
        try:
            # Try multiple environment variable names and load .env if needed
            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or os.getenv("openai_api_key")
            
            if not api_key:
                raise ValueError("OpenAI API key not found in environment variables")
            
            print(f"DEBUG: Using OpenAI API key: {api_key[:10]}...{api_key[-4:]}")
            
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name="text-embedding-3-small"
            )
            print("DEBUG: OpenAI embedding function initialized")
        except Exception as e:
            print(f"DEBUG: Failed to initialize OpenAI embeddings: {e}")
            raise e
        
        # Cross-encoder for reranking
        try:
            self.cross_encoder_model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            self.cross_encoder_device = "cuda" if torch.cuda.is_available() else "cpu"
            self.cross_encoder = CrossEncoder(
                self.cross_encoder_model_name, 
                device=self.cross_encoder_device
            )
            print(f"DEBUG: Cross-encoder initialized on {self.cross_encoder_device}")
        except Exception as e:
            print(f"DEBUG: Failed to initialize cross-encoder: {e}")
            self.cross_encoder = None
        
        # Course collection mapping - now stores both client and collection
        self.course_collections = {}
        self._initialize_course_collections()
        
        print(f"DEBUG: RAG Tool initialized with {len(self.course_collections)} course collections")

    def _initialize_course_collections(self):
        """
        Initialize course collections using the new per-course directory structure
        Each course gets its own ChromaDB client pointing to its dedicated directory
        FIXED: Compatible with ChromaDB v0.5.x API (returns Collection objects, not strings)
        """
        # Define course configurations
        course_configs = {
            "CMP511": {
                "description": "Machine Learning and AI course materials"
            },
            "CMP202": {
                "description": "Data Structures and Algorithms 2 course materials"
            },
            "PSY555": {
                "description": "Psychology: in what ways are we all the same? course materials"
            },
            "CMP304": {
                "description": "Artificial Intelligence course materials"
            },
            "MAT201": {
                "description": "Applied Mathematics 2 course materials"
            },
            "CMP203": {
                "description": "Graphics Programming course materials"
            }
        }
        
        # Scan the base directory for existing course directories
        try:
            if os.path.exists(self.base_chroma_dir):
                existing_course_dirs = [
                    d for d in os.listdir(self.base_chroma_dir) 
                    if os.path.isdir(os.path.join(self.base_chroma_dir, d)) and not d.startswith('.')
                ]
                print(f"DEBUG: Found existing course directories: {existing_course_dirs}")
            else:
                existing_course_dirs = []
        except Exception as e:
            print(f"DEBUG: Error scanning course directories: {e}")
            existing_course_dirs = []
        
        # Initialize each course that has a corresponding directory
        for course_code, config in course_configs.items():
            if course_code in existing_course_dirs:
                try:
                    # Each course gets its own ChromaDB client pointing to its directory
                    course_db_path = os.path.join(self.base_chroma_dir, course_code)
                    print(f"DEBUG: Initializing ChromaDB client for {course_code} at: {course_db_path}")
                    
                    # Create a dedicated ChromaDB client for this course
                    course_client = chromadb.PersistentClient(path=course_db_path)
                    
                    # FIXED: Handle both ChromaDB v0.5.x (returns Collection objects) and v0.6.x (returns strings)
                    collections = course_client.list_collections()
                    print(f"DEBUG: Course {course_code} has {len(collections)} collections")
                    
                    if collections:
                        # Check what type of objects we got back
                        first_collection = collections[0]
                        
                        # Handle both API versions
                        if hasattr(first_collection, 'name'):
                            # v0.5.x - Collection object with .name attribute
                            collection_name = first_collection.name
                            print(f"DEBUG: Using collection '{collection_name}' for course {course_code} (v0.5.x API)")
                        else:
                            # v0.6.x - String collection name
                            collection_name = first_collection
                            print(f"DEBUG: Using collection '{collection_name}' for course {course_code} (v0.6.x API)")
                        
                        course_collection = course_client.get_collection(
                            name=collection_name,  # Use the string name
                            embedding_function=self.embedding_function
                        )
                        
                        # Get collection statistics
                        try:
                            doc_count = course_collection.count()
                            print(f"DEBUG: Collection for {course_code} has {doc_count} documents")
                        except Exception as e:
                            print(f"DEBUG: Error getting document count for {course_code}: {e}")
                            doc_count = 0
                        
                        # Store both the client and collection for this course
                        if doc_count > 0:
                            self.course_collections[course_code] = {
                                "client": course_client,
                                "collection": course_collection,
                                "collection_name": collection_name,  # Store the string name
                                "description": config["description"],
                                "document_count": doc_count,
                                "db_path": course_db_path
                            }
                            print(f"DEBUG: Successfully initialized {course_code} with {doc_count} documents")
                        else:
                            print(f"DEBUG: Skipping {course_code} - collection is empty")
                    else:
                        print(f"DEBUG: No collections found in {course_code} database")
                        
                except Exception as e:
                    print(f"DEBUG: Error initializing course {course_code}: {e}")
                    import traceback
                    traceback.print_exc()  # Add full traceback for debugging
            else:
                print(f"DEBUG: Directory for course {course_code} not found, skipping")
        
        print(f"DEBUG: Successfully initialized {len(self.course_collections)} course collections")
        
        # Print summary of initialized courses
        for course_code, info in self.course_collections.items():
            print(f"DEBUG: {course_code} -> {info['document_count']} docs at {info['db_path']}")
            
  

    async def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute RAG retrieval with enhanced error handling"""
        try:
            query = parameters.get("query", "").strip()
            course = parameters.get("course", "").strip()
            max_results = parameters.get("max_results", 5)
            use_reranking = parameters.get("use_reranking", True)
            
            print(f"DEBUG: RAG execute called with query='{query}', course='{course}'")
            print(f"DEBUG: Available courses: {list(self.course_collections.keys())}")
            
            # Validate inputs
            if not query:
                print("DEBUG: RAG failed - empty query")
                return {
                    "success": False,
                    "error": "Query parameter is required and cannot be empty"
                }
            
            if not course:
                print("DEBUG: RAG failed - empty course")
                return {
                    "success": False,
                    "error": "Course parameter is required",
                    "available_courses": list(self.course_collections.keys())
                }
            
            if course not in self.course_collections:
                print(f"DEBUG: RAG failed - course '{course}' not available")
                return {
                    "success": False,
                    "error": f"Course '{course}' not available. Available courses: {list(self.course_collections.keys())}",
                    "available_courses": list(self.course_collections.keys())
                }
            
            print(f"DEBUG: RAG retrieval for course '{course}' with query: '{query}'")
            
            # Get the appropriate collection for this course
            course_info = self.course_collections[course]
            collection = course_info["collection"]
            print(f"DEBUG: Using collection with {course_info['document_count']} documents")
            
            # Test the collection with a simple query first
            try:
                test_result = collection.query(query_texts=[query], n_results=1)
                # print(f"DEBUG: Test query returned: {len(test_result.get('documents', [[]])[0])} documents")
                # if test_result.get('documents') and test_result['documents'][0]:
                #     print(f"DEBUG: First result preview: {test_result['documents'][0][0][:100]}...")
            except Exception as e:
                print(f"DEBUG: Test query failed: {e}")
                return {
                    "success": False,
                    "error": f"Collection query failed: {str(e)}"
                }
            
            # Perform retrieval using the course-specific collection
            if use_reranking and self.cross_encoder:
                print("DEBUG: Using two-stage retrieval")
                results = await self._two_stage_retrieve(collection, query, max_results)
            else:
                print("DEBUG: Using simple retrieval")
                results = await self._simple_retrieve(collection, query, max_results)
            
            print(f"DEBUG: RAG retrieval completed with {len(results)} results")
            
            result = {
                "success": True,
                "tool": self.tool_name,
                "course": course,
                "query": query,
                "num_results": len(results),
                "results": results,
                "collection_info": {
                    "total_documents": course_info.get("document_count", 0),
                    "description": course_info.get("description", ""),
                    "collection_name": course_info.get("collection_name", ""),
                    "db_path": course_info.get("db_path", "")
                }
            }
            
            print(f"DEBUG: RAG returning result: success={result['success']}, num_results={result['num_results']}")
            return result
            
        except Exception as e:
            print(f"DEBUG: RAG retrieval error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": f"RAG retrieval failed: {str(e)}",
                "available_courses": list(self.course_collections.keys()) if hasattr(self, 'course_collections') else []
            }
    
    
    async def _two_stage_retrieve(self, collection, query: str, max_results: int) -> List[Dict]:
        """Two-stage retrieval: vector similarity + cross-encoder reranking"""
        try:
            # Stage 1: Vector similarity (get more results for reranking)
            initial_k = min(max_results * 4, 20)  # Get 4x more for reranking
            
            print(f"DEBUG: Performing vector search with k={initial_k}")
            
            initial_results = collection.query(
                query_texts=[query],
                n_results=initial_k
            )
            
            # DEBUG BLOCK (Uncomment to see display)
            # print(f"DEBUG: Raw ChromaDB results structure:")
            # print(f"DEBUG: - Keys: {list(initial_results.keys())}")
            # print(f"DEBUG: - Documents type: {type(initial_results.get('documents'))}")
            # print(f"DEBUG: - Documents length: {len(initial_results.get('documents', []))}")
            # if initial_results.get('documents') and initial_results['documents'][0]:
            #     print(f"DEBUG: - First doc preview: {str(initial_results['documents'][0][0])[:200]}...")
            #     print(f"DEBUG: - First doc type: {type(initial_results['documents'][0][0])}")
            # print(f"DEBUG: - IDs: {initial_results.get('ids', [])[:2]}")  # Show first 2 IDs
            # print(f"DEBUG: - Metadatas: {initial_results.get('metadatas', [])[:1]}")  # Show first metadata
            
            if not initial_results["documents"] or not initial_results["documents"][0]:
                print("DEBUG: No documents returned from vector search")
                return []
            
            # Prepare candidates for reranking
            candidates = []
            for i in range(len(initial_results["ids"][0])):
                doc_text = initial_results["documents"][0][i]
                doc_metadata = initial_results["metadatas"][0][i] or {}
                
                # DEBUG: Show what we're extracting
                # print(f"DEBUG: Doc {i} - Text type: {type(doc_text)}, Text preview: {str(doc_text)[:100]}...")
                
                candidates.append({
                    "id": initial_results["ids"][0][i],
                    "text": doc_text,  # This should be the actual content
                    "metadata": doc_metadata,
                    "vector_distance": initial_results["distances"][0][i]
                })
            
            print(f"DEBUG: Retrieved {len(candidates)} candidates for reranking")
            
            # Stage 2: Cross-encoder reranking
            if len(candidates) > 1 and self.cross_encoder:
                try:
                    cross_input = [(query, doc["text"]) for doc in candidates]
                    scores = self.cross_encoder.predict(cross_input)
                    
                    # Attach reranking scores
                    for doc, score in zip(candidates, scores):
                        doc["rerank_score"] = float(score)
                    
                    # Sort by reranking score
                    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
                    print(f"DEBUG: Reranked candidates by cross-encoder scores")
                except Exception as e:
                    print(f"DEBUG: Cross-encoder reranking failed: {e}")
                    # Fallback to vector similarity ranking
                    for doc in candidates:
                        doc["rerank_score"] = 1.0 - doc["vector_distance"]  # Convert distance to score
                    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
            else:
                # Single result or no cross-encoder, use vector similarity
                for doc in candidates:
                    doc["rerank_score"] = 1.0 - doc["vector_distance"]  # Convert distance to score
            
            # Return top results
            final_results = []
            for doc in candidates[:max_results]:
                final_result = {
                    "chunk_id": doc["id"],
                    "content": doc["text"],  # This is where the problem might be
                    "metadata": doc["metadata"],
                    "vector_distance": doc["vector_distance"],
                    "rerank_score": doc["rerank_score"],
                    "relevance": "high" if doc["rerank_score"] > 0.5 else "medium"
                }
                
                # # DEBUG: Show final result content
                # print(f"DEBUG: Final result content type: {type(final_result['content'])}")
                # print(f"DEBUG: Final result content preview: {str(final_result['content'])[:100]}...")
                
                final_results.append(final_result)
            
            print(f"DEBUG: Returning {len(final_results)} final results")
            return final_results
            
        except Exception as e:
            print(f"DEBUG: Error in two-stage retrieval: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to simple retrieval
            return await self._simple_retrieve(collection, query, max_results)

    

    async def _simple_retrieve(self, collection, query: str, max_results: int) -> List[Dict]:
        """Simple vector similarity retrieval"""
        try:
            print(f"DEBUG: Performing simple vector search with max_results={max_results}")
            
            results = collection.query(
                query_texts=[query],
                n_results=max_results
            )
            
            if not results["documents"] or not results["documents"][0]:
                print("DEBUG: No documents returned from simple search")
                return []
            
            final_results = []
            for i in range(len(results["ids"][0])):
                final_results.append({
                    "chunk_id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] or {},
                    "vector_distance": results["distances"][0][i],
                    "relevance": "medium"
                })
            
            print(f"DEBUG: Simple retrieval returned {len(final_results)} results")
            return final_results
            
        except Exception as e:
            print(f"DEBUG: Error in simple retrieval: {e}")
            return []
    
    def get_schema(self) -> Dict[str, Any]:
        """Return the tool schema for MCP registration"""
        return {
            "name": self.tool_name,
            "description": self.description,
            "parameters": {
                "query": {
                    "type": "string",
                    "description": "Search query for retrieving relevant content",
                    "required": True
                },
                "course": {
                    "type": "string", 
                    "description": f"Course code. Available: {list(self.course_collections.keys())}",
                    "required": True
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5
                },
                "use_reranking": {
                    "type": "boolean",
                    "description": "Whether to use cross-encoder reranking (default: True)",
                    "default": True
                }
            }
        }
    
    def get_available_courses(self) -> List[str]:
        """Get list of available course collections"""
        return list(self.course_collections.keys())
    
    async def get_collection_stats(self, course: str) -> Dict[str, Any]:
        """Get statistics about a course collection"""
        if course not in self.course_collections:
            return {"error": f"Course '{course}' not found"}
        
        try:
            course_info = self.course_collections[course]
            collection = course_info["collection"]
            count = collection.count()
            
            return {
                "course": course,
                "document_count": count,
                "description": course_info["description"],
                "collection_name": course_info["collection_name"],
                "db_path": course_info["db_path"]
            }
        except Exception as e:
            return {"error": f"Failed to get stats: {str(e)}"}
            

