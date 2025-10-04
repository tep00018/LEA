# src/mcp/tools/document_ingestion.py
"""
Document Ingestion System for LEA RAG
Processes course documents using modular, per-course directory structure
"""

import os
import json
import hashlib
import asyncio
import nltk
import re
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

class DocumentIngestionSystem:
    """
    Handles document processing and ingestion into course-specific RAG collections
    Uses modular directory structure for better organization and isolation
    """
    
    def __init__(self, base_data_dir: str = "data"):
        """Initialize the ingestion system with modular directory structure"""
        self.base_data_dir = Path(base_data_dir)
        
        # Define the new modular directory structure
        # Each major category gets its own subdirectory with module organization
        self.org_docs_dir = self.base_data_dir / "org_docs"
        self.org_docs_archive_dir = self.base_data_dir / "org_docs_archive"
        self.md_docs_dir = self.base_data_dir / "md_docs"
        self.signatures_dir = self.base_data_dir / "signatures"
        self.metadata_dir = self.base_data_dir / "metadata"
        self.chroma_data_dir = self.base_data_dir / "chroma_data"
        
        # Create the base directory structure
        # This ensures all necessary directories exist before we start processing
        for directory in [self.org_docs_dir, self.org_docs_archive_dir, 
                         self.md_docs_dir, self.signatures_dir, 
                         self.metadata_dir, self.chroma_data_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize OpenAI embedding function once for all modules
        # This ensures consistency across all course collections
        try:
            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not found in environment variables")
                
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name="text-embedding-3-small"
            )
            print("DEBUG: OpenAI embedding function initialized successfully")
        except Exception as e:
            print(f"ERROR: Failed to initialize embedding function: {e}")
            raise e
        
        # Store module-specific ChromaDB clients to avoid recreating them
        # This improves performance when processing multiple files from the same module
        self.module_clients = {}
        
        print(f"DEBUG: Document Ingestion System initialized with modular structure")
        print(f"DEBUG: Base data directory: {self.base_data_dir}")
        print(f"DEBUG: Organizational structure ready for module-based processing")
    
    def discover_available_modules(self) -> List[str]:
        """
        Discover all available modules by scanning the md_docs directory
        This allows the system to automatically detect new courses without configuration
        """
        modules = []
        if self.md_docs_dir.exists():
            # Look for subdirectories in md_docs - each represents a module
            for item in self.md_docs_dir.iterdir():
                if item.is_dir():
                    modules.append(item.name)
        
        modules.sort()  # Ensure consistent ordering
        print(f"DEBUG: Discovered {len(modules)} modules: {modules}")
        return modules
    
    def get_module_paths(self, module: str) -> Dict[str, Path]:
        """
        Get all relevant paths for a specific module
        This centralizes path management and makes the code more maintainable
        """
        return {
            "org_docs": self.org_docs_dir / module,
            "org_docs_archive": self.org_docs_archive_dir / module,
            "md_docs": self.md_docs_dir / module,
            "signatures_file": self.signatures_dir / module / f"md_doc_signatures_{module}.json",
            "metadata_file": self.metadata_dir / module / f"doc_metadata_{module}.json",
            "chroma_data": self.chroma_data_dir / module
        }
    
    def ensure_module_directories(self, module: str):
        """
        Ensure all necessary directories exist for a module
        Creates the full directory structure if it doesn't exist
        """
        paths = self.get_module_paths(module)
        
        # Create all directories except the files
        for key, path in paths.items():
            if key.endswith('_file'):
                # For files, create the parent directory
                path.parent.mkdir(parents=True, exist_ok=True)
            else:
                # For directories, create the directory itself
                path.mkdir(parents=True, exist_ok=True)
        
        print(f"DEBUG: Ensured directory structure exists for module: {module}")
    
    def load_module_signatures(self, module: str) -> Dict[str, Any]:
        """Load existing file signatures for a specific module"""
        paths = self.get_module_paths(module)
        signatures_file = paths["signatures_file"]
        
        if signatures_file.exists():
            try:
                with open(signatures_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"WARNING: Failed to load signatures for {module}: {e}")
                return {}
        return {}
    
    def save_module_signatures(self, module: str, sig_data: Dict[str, Any]):
        """Save updated signature data for a specific module"""
        paths = self.get_module_paths(module)
        signatures_file = paths["signatures_file"]
        
        # Ensure the parent directory exists
        signatures_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(signatures_file, "w", encoding="utf-8") as f:
                json.dump(sig_data, f, indent=2)
            print(f"DEBUG: Saved signatures for module {module}")
        except Exception as e:
            print(f"ERROR: Failed to save signatures for {module}: {e}")
    
    def load_module_metadata(self, module: str) -> Dict[str, Any]:
        """Load document metadata for a specific module"""
        paths = self.get_module_paths(module)
        metadata_file = paths["metadata_file"]
        
        if metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"WARNING: Failed to load metadata for {module}: {e}")
                return {}
        return {}
    
    def compute_signature(self, file_path: Path) -> str:
        """Compute MD5 signature for change detection"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            print(f"ERROR: Failed to compute signature for {file_path}: {e}")
            return "error"
    
    def get_or_create_module_client(self, module: str) -> chromadb.PersistentClient:
        """
        Get or create a ChromaDB client for a specific module
        Uses caching to avoid recreating clients unnecessarily
        """
        if module not in self.module_clients:
            paths = self.get_module_paths(module)
            chroma_path = paths["chroma_data"]
            
            # Ensure the ChromaDB directory exists
            chroma_path.mkdir(parents=True, exist_ok=True)
            
            try:
                # Create a dedicated ChromaDB client for this module
                client = chromadb.PersistentClient(path=str(chroma_path))
                self.module_clients[module] = client
                print(f"DEBUG: Created ChromaDB client for module {module} at {chroma_path}")
            except Exception as e:
                print(f"ERROR: Failed to create ChromaDB client for {module}: {e}")
                raise e
        
        return self.module_clients[module]
    
    def get_or_create_module_collection(self, module: str) -> chromadb.Collection:
        """
        Get or create a ChromaDB collection for a module
        Each module gets exactly one collection named after the module
        """
        client = self.get_or_create_module_client(module)
        collection_name = module  # Simple, clean naming: collection name matches module name
        
        try:
            # Try to get existing collection
            collection = client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            print(f"DEBUG: Using existing collection for module {module}")
        except:
            # Create new collection if it doesn't exist
            try:
                collection = client.create_collection(
                    name=collection_name,
                    embedding_function=self.embedding_function
                )
                print(f"DEBUG: Created new collection for module {module}")
            except Exception as e:
                print(f"ERROR: Failed to create collection for {module}: {e}")
                raise e
        
        return collection
    
    def normalize_course_code(self, course_code: str) -> str:
        """
        Normalize course codes to match directory names
        This ensures consistency between filename parsing and directory structure
        """
        # Convert common variations to standard format
        code_mappings = {
            "CMP511": "CMP511",
            "CMP202": "CMP202", 
            "PSY555": "PSY555",
            "CMP304": "CMP304",
            "MAT201": "MAT201",
            "CMP203": "CMP203",
            # Add more mappings as needed
        }
        
        # Try exact match first
        if course_code in code_mappings:
            return code_mappings[course_code]
        
        # Fallback to the original code
        return course_code
    
    def extract_course_from_filename(self, filename: str) -> str:
        """
        Extract course code from filename with improved pattern matching
        This is crucial for automatically organizing files into the correct modules
        """
        # Remove file extension for cleaner pattern matching
        name_without_ext = Path(filename).stem.upper()
        
        # Define comprehensive course code patterns
        course_patterns = [
            r"^(CMP\d+)",           # CMP511, CMP202, etc.
            r"^(PSY\d+)",           # PSY555, etc.
            r"^(MAT\d+)",           # MAT201, etc.
            r"^(ENG\d+)",           # ENG101, etc.
            r"^(CS\d+)",            # CS101, etc.
            r"(CMP\d+)",            # CMP code anywhere in name
            r"(PSY\d+)",            # PSY code anywhere in name
        ]
        
        for pattern in course_patterns:
            match = re.search(pattern, name_without_ext)
            if match:
                course_code = match.group(1)
                return self.normalize_course_code(course_code)
        
        # If no pattern matches, try to use the directory structure
        # This handles cases where files are already organized by module
        return "General"
    
    def advanced_cross_page_chunking(
        self,
        file_content: str,
        file_metadata: Dict[str, Any],
        chunk_token_limit: int = 512,
        token_overlap: int = 128
    ) -> List[Dict[str, Any]]:
        """
        Advanced chunking that can cross page boundaries while tracking page ranges
        This method preserves semantic coherence while maintaining page traceability
        """
        is_pdf = file_metadata.get("extension", "").lower() == ".pdf"
        org_filename = file_metadata.get("org_filename", "UnknownFile")
        
        # Extract page boundaries if PDF - look for page break markers
        page_break_pattern = r"\[\[PAGE_BREAK_(\d+)\]\]"
        page_boundaries = []
        
        if is_pdf:
            # Find all page break markers and record their positions
            matches = list(re.finditer(page_break_pattern, file_content))
            for m in matches:
                page_num = int(m.group(1))
                start_offset = m.start()
                page_boundaries.append((start_offset, page_num))
            
            # Sort by position and remove the markers from content
            page_boundaries.sort(key=lambda x: x[0])
            file_content = re.sub(page_break_pattern, "", file_content)
        
        # Split content into paragraphs for better semantic coherence
        paragraphs = re.split(r"\n\s*\n", file_content.strip())
        
        final_chunks = []
        current_tokens = []
        current_chunk_sentences = []
        running_char_offset = 0
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                running_char_offset += len(paragraph) + 2
                continue
            
            # Use NLTK for proper sentence tokenization
            sentences = nltk.sent_tokenize(paragraph)
            
            for sentence in sentences:
                # Tokenize the sentence to count tokens accurately
                s_tokens = nltk.word_tokenize(sentence)
                s_length = len(sentence)
                
                # Check if adding this sentence would exceed our token limit
                if len(current_tokens) + len(s_tokens) > chunk_token_limit:
                    # Time to finalize the current chunk
                    chunk_text = " ".join(current_chunk_sentences)
                    
                    # Calculate character offsets for page range determination
                    chunk_start_offset = running_char_offset - len(chunk_text)
                    chunk_end_offset = running_char_offset
                    page_range_str = self._determine_page_range(
                        chunk_start_offset, chunk_end_offset, page_boundaries
                    )
                    
                    # Create the chunk with comprehensive metadata
                    final_chunks.append({
                        "text": chunk_text,
                        "metadata": {
                            "file_name": org_filename,
                            "summary": file_metadata.get("summary", "No summary available"),
                            "title": file_metadata.get("title", "Untitled"),
                            "num_pages": file_metadata.get("num_pages", 0),
                            "page_range": page_range_str,
                            "module": file_metadata.get("module", "General"),
                            "chunk_index": len(final_chunks),
                            "file_type": file_metadata.get("file_type", "Unknown"),
                            "extension": file_metadata.get("extension", ".md")
                        }
                    })
                    
                    # Handle token overlap for better context continuity
                    overlap_tokens = current_tokens[-token_overlap:] if token_overlap < len(current_tokens) else current_tokens
                    overlap_text = " ".join(overlap_tokens)
                    
                    # Reset for next chunk with overlap
                    current_tokens = list(overlap_tokens)
                    current_chunk_sentences = [overlap_text] if overlap_text else []
                
                # Add current sentence to the growing chunk
                current_tokens.extend(s_tokens)
                current_chunk_sentences.append(sentence)
                running_char_offset += s_length + 1
            
            # Account for paragraph separation
            running_char_offset += 2
        
        # Don't forget to finalize the last chunk
        if current_tokens:
            chunk_text = " ".join(current_chunk_sentences)
            chunk_length = len(chunk_text)
            chunk_start_offset = running_char_offset - chunk_length
            chunk_end_offset = running_char_offset
            page_range_str = self._determine_page_range(
                chunk_start_offset, chunk_end_offset, page_boundaries
            )
            
            final_chunks.append({
                "text": chunk_text,
                "metadata": {
                    "file_name": org_filename,
                    "summary": file_metadata.get("summary", "No summary available"),
                    "title": file_metadata.get("title", "Untitled"),
                    "num_pages": file_metadata.get("num_pages", 0),
                    "page_range": page_range_str,
                    "module": file_metadata.get("module", "General"),
                    "chunk_index": len(final_chunks),
                    "file_type": file_metadata.get("file_type", "Unknown"),
                    "extension": file_metadata.get("extension", ".md")
                }
            })
        
        return final_chunks
    
    def _determine_page_range(self, start_offset: int, end_offset: int, page_boundaries: List[Tuple[int, int]]) -> str:
        """
        Determine which pages a chunk covers based on character offsets
        This provides accurate page tracking for citations and references
        """
        if not page_boundaries:
            return "N/A"
        
        covered_pages = set()
        
        # Check each page boundary to see if the chunk overlaps with it
        for i in range(len(page_boundaries)):
            page_offset, page_num = page_boundaries[i]
            
            # Determine the end of this page (start of next page or end of document)
            if i < len(page_boundaries) - 1:
                next_offset = page_boundaries[i + 1][0]
            else:
                next_offset = float("inf")  # Last page extends to end of document
            
            # Check if chunk overlaps with this page
            if end_offset >= page_offset and start_offset < next_offset:
                covered_pages.add(page_num)
        
        if not covered_pages:
            return "N/A"
        
        # Format the page range appropriately
        min_page = min(covered_pages)
        max_page = max(covered_pages)
        if min_page == max_page:
            return str(min_page)
        else:
            return f"{min_page}-{max_page}"
    
    async def process_module(self, module: str) -> Dict[str, Any]:
        """
        Process all documents for a specific module
        This is the core processing function for individual modules
        """
        print(f"\n=== Processing Module: {module} ===")
        
        # Ensure the module directory structure exists
        self.ensure_module_directories(module)
        
        # Get module-specific paths and data
        paths = self.get_module_paths(module)
        sig_data = self.load_module_signatures(module)
        doc_metadata_map = self.load_module_metadata(module)
        
        # Check if the md_docs directory exists for this module
        md_docs_path = paths["md_docs"]
        if not md_docs_path.exists():
            print(f"WARNING: No md_docs directory found for module {module}")
            return {"processed": 0, "skipped": 0, "error": "No md_docs directory"}
        
        processed_count = 0
        skipped_count = 0
        
        # Process all .md files in this module's directory
        for md_file in md_docs_path.glob("*.md"):
            filename = md_file.name
            file_sig = self.compute_signature(md_file)
            
            # Skip if file hasn't changed (optimization for large document sets)
            if filename in sig_data and sig_data[filename].get("signature") == file_sig:
                print(f"[SKIP] {filename} - unchanged")
                skipped_count += 1
                continue
            
            # Read the file content
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                print(f"ERROR: Failed to read {filename}: {e}")
                continue
            
            # Find corresponding metadata from the original document
            original_filename = self._find_original_filename(filename, doc_metadata_map)
            meta_info = doc_metadata_map.get(original_filename, {})
            
            # Build comprehensive metadata for this file
            file_metadata = {
                "file_name": filename,
                "org_filename": original_filename,
                "title": meta_info.get("title", Path(filename).stem),
                "num_pages": meta_info.get("num_pages", 0),
                "extension": meta_info.get("extension", ".md"),
                "summary": meta_info.get("summary", "No summary available"),
                "file_type": meta_info.get("file_type", "Unknown"),
                "module": module  # Explicitly track which module this belongs to
            }
            
            # Chunk the content using our advanced chunking algorithm
            try:
                chunks = self.advanced_cross_page_chunking(content, file_metadata)
                print(f"DEBUG: Created {len(chunks)} chunks for {filename}")
            except Exception as e:
                print(f"ERROR: Failed to chunk {filename}: {e}")
                continue
            
            # Get the module's ChromaDB collection
            try:
                collection = self.get_or_create_module_collection(module)
            except Exception as e:
                print(f"ERROR: Failed to get collection for module {module}: {e}")
                continue
            
            # Upsert each chunk into the collection
            chunks_processed = 0
            for i, chunk in enumerate(chunks):
                doc_id = f"{filename}_{i}"
                
                # Validate chunk content before upserting
                if not chunk["text"] or not isinstance(chunk["text"], str):
                    print(f"WARNING: Skipping invalid chunk {i} from {filename}")
                    continue
                
                try:
                    collection.upsert(
                        documents=[chunk["text"]],
                        metadatas=[chunk["metadata"]],
                        ids=[doc_id]
                    )
                    chunks_processed += 1
                except Exception as e:
                    print(f"ERROR: Failed to upsert chunk {i} from {filename}: {e}")
                    continue
            
            # Update signature tracking for this file
            sig_data[filename] = {
                "signature": file_sig,
                "file_name": filename,
                "module": module,
                "chunks_created": chunks_processed,
                "last_processed": str(Path(__file__).stat().st_mtime)  # Timestamp for debugging
            }
            
            print(f"[PROCESSED] {filename} -> {chunks_processed} chunks added to {module} collection")
            processed_count += 1
        
        # Save updated signatures for this module
        self.save_module_signatures(module, sig_data)
        
        result = {
            "module": module,
            "processed": processed_count,
            "skipped": skipped_count,
            "total_files": processed_count + skipped_count
        }
        
        print(f"=== Module {module} Complete: {processed_count} processed, {skipped_count} skipped ===")
        return result
    
    async def process_all_modules(self) -> Dict[str, Any]:
        """
        Process all available modules
        This is the main entry point for the ingestion system
        """
        print("Starting modular document ingestion process...")
        
        # Discover all available modules
        modules = self.discover_available_modules()
        
        if not modules:
            print("WARNING: No modules found in md_docs directory")
            return {"error": "No modules found", "modules_processed": 0}
        
        # Process each module independently
        results = {}
        total_processed = 0
        total_skipped = 0
        
        for module in modules:
            try:
                module_result = await self.process_module(module)
                results[module] = module_result
                total_processed += module_result.get("processed", 0)
                total_skipped += module_result.get("skipped", 0)
            except Exception as e:
                print(f"ERROR: Failed to process module {module}: {e}")
                results[module] = {"error": str(e), "processed": 0, "skipped": 0}
        
        # Compile overall statistics
        summary = {
            "success": True,
            "modules_processed": len(modules),
            "total_files_processed": total_processed,
            "total_files_skipped": total_skipped,
            "module_results": results,
            "available_modules": modules
        }
        
        print(f"\n=== INGESTION COMPLETE ===")
        print(f"Modules processed: {len(modules)}")
        print(f"Total files processed: {total_processed}")
        print(f"Total files skipped: {total_skipped}")
        
        return summary
    
    def _find_original_filename(self, md_filename: str, doc_metadata_map: Dict) -> str:
        """
        Find the original filename that corresponds to this markdown file
        This helps maintain the connection between processed and original documents
        """
        # Try different common extensions to find the original file
        for ext in [".pdf", ".docx", ".pptx", ".doc", ".ppt", ".txt", ".h", ".cpp", ".xlsx", ".ipynb"]:
            candidate = md_filename.replace(".md", ext)
            if candidate in doc_metadata_map:
                return candidate
        
        # If no match found, return the original markdown filename
        return md_filename
    
    async def get_ingestion_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the ingestion process across all modules
        This provides valuable insights into the state of your document collections
        """
        modules = self.discover_available_modules()
        
        overall_stats = {
            "total_modules": len(modules),
            "module_details": {},
            "grand_totals": {"files": 0, "chunks": 0}
        }
        
        for module in modules:
            # Load signature data for this module to get statistics
            sig_data = self.load_module_signatures(module)
            
            module_stats = {
                "files_tracked": len(sig_data),
                "total_chunks": 0,
                "last_processed_files": []
            }
            
            # Aggregate chunk counts and find recently processed files
            for filename, data in sig_data.items():
                chunks = data.get("chunks_created", 0)
                module_stats["total_chunks"] += chunks
                
                # Track recently processed files (those with signature data)
                if "last_processed" in data:
                    module_stats["last_processed_files"].append({
                        "filename": filename,
                        "chunks": chunks
                    })
            
            overall_stats["module_details"][module] = module_stats
            overall_stats["grand_totals"]["files"] += module_stats["files_tracked"]
            overall_stats["grand_totals"]["chunks"] += module_stats["total_chunks"]
        
        return overall_stats
        