# File: rag_library_creation.py
#!/usr/bin/env python3
"""
Unified Document Processing Pipeline
Converts various document formats (including videos) to markdown,
then chunks, embeds, and saves to ChromaDB.

Usage: python process_module.py <module_code>
Example: python process_module.py PSY555
"""

import os
import sys
import json
import hashlib
import re
import warnings
import argparse
import tempfile
import traceback
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Suppress warnings
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")
warnings.filterwarnings("ignore", module="whisper.*")
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ["CHROMA_TELEMETRY_OPTOUT"] = "true"

# Import required libraries
import whisper
import nltk
from dotenv import load_dotenv
from markitdown import MarkItDown
from openai import OpenAI
from pdfminer.high_level import extract_text
from pdfminer.layout import LAParams
from chromadb import PersistentClient
from chromadb.utils import embedding_functions

# Load environment variables
load_dotenv()

# Download NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

class DocumentProcessor:
    """Main class for processing documents through the complete pipeline."""
    
    def __init__(self, module_code: str):
        """Initialize the processor with module-specific paths."""
        self.module = module_code
        
        # Define directory structure
        self.input_dir = f"data/org_docs/{module_code}"
        self.output_dir = f"data/md_docs/{module_code}"
        self.chroma_dir = f"data/chroma_data/{module_code}"
        self.meta_dir = f"data/metadata"
        self.meta_json_path = f"{self.meta_dir}/doc_metadata_{module_code}.json"
        self.error_log_path = f"{self.meta_dir}/errors_{module_code}.json"
        
        # Create necessary directories
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.chroma_dir, exist_ok=True)
        os.makedirs(self.meta_dir, exist_ok=True)
        
        # Initialize OpenAI client
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.openai_client = OpenAI()
        self.md_converter = MarkItDown(
            llm_client=self.openai_client, 
            llm_model="gpt-4o"
        )
        
        # Initialize Whisper model
        print("Loading Whisper model...")
        self.whisper_model = whisper.load_model("base")
        
        # Initialize ChromaDB
        self.chroma_client = PersistentClient(path=self.chroma_dir)
        self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self.openai_api_key,
            model_name="text-embedding-3-small"
        )
        
        # Initialize or get collection
        self.collection = self._get_or_create_collection()
        
        # Load existing metadata and errors
        self.metadata = self._load_metadata()
        self.errors = self._load_errors()
    
    def _load_metadata(self) -> Dict:
        """Load existing metadata from disk."""
        if os.path.exists(self.meta_json_path):
            with open(self.meta_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def _save_metadata(self):
        """Save metadata to disk."""
        with open(self.meta_json_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2)
    
    def _load_errors(self) -> Dict:
        """Load existing error log from disk."""
        if os.path.exists(self.error_log_path):
            with open(self.error_log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def _save_errors(self):
        """Save error log to disk."""
        with open(self.error_log_path, "w", encoding="utf-8") as f:
            json.dump(self.errors, f, indent=2)
    
    def _log_error(self, file_name: str, error_type: str, error_message: str):
        """Log an error for a specific file."""
        self.errors[file_name] = {
            "error_type": error_type,
            "error_message": str(error_message),
            "timestamp": str(sys.exc_info()[0]) if sys.exc_info()[0] else "Unknown"
        }
        self._save_errors()
    
    def _compute_signature(self, file_path: str) -> str:
        """Compute MD5 signature of a file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _get_or_create_collection(self):
        """Get or create ChromaDB collection."""
        try:
            collection = self.chroma_client.get_collection(
                name=self.module,
                embedding_function=self.embedding_function
            )
            print(f"Using existing ChromaDB collection: {self.module}")
        except:
            collection = self.chroma_client.create_collection(
                name=self.module,
                embedding_function=self.embedding_function
            )
            print(f"Created new ChromaDB collection: {self.module}")
        return collection
    
    def _transcribe_video(self, video_path: str) -> Tuple[str, str]:
        """Transcribe video file using Whisper."""
        print(f"  Transcribing video: {os.path.basename(video_path)}")
        
        try:
            result = self.whisper_model.transcribe(video_path)
            
            # Create transcript with metadata
            transcript_text = f"# Video Transcript: {os.path.basename(video_path)}\n\n"
            transcript_text += f"**Duration:** {result.get('duration', 'unknown')} seconds\n"
            transcript_text += f"**Language:** {result.get('language', 'unknown')}\n\n"
            transcript_text += "## Transcript\n\n"
            transcript_text += result["text"]
            
            # Add timestamped segments if needed
            if result.get("segments"):
                transcript_text += "\n\n## Timestamped Segments\n\n"
                for segment in result["segments"]:
                    start_time = self._seconds_to_time(segment["start"])
                    end_time = self._seconds_to_time(segment["end"])
                    transcript_text += f"[{start_time} - {end_time}] {segment['text'].strip()}\n\n"
            
            return transcript_text, result["text"]
            
        except Exception as e:
            print(f"  Error transcribing video: {e}")
            error_text = f"# Error: Video Transcription Failed\n\n"
            error_text += f"File: {os.path.basename(video_path)}\n"
            error_text += f"Error: {str(e)}"
            return error_text, ""
    
    def _seconds_to_time(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _convert_pdf_with_pages(self, pdf_path: str) -> Tuple[str, List, int]:
        """Convert PDF to markdown with page markers."""
        try:
            laparams = LAParams()
            pdf_text = extract_text(pdf_path, laparams=laparams)
            
            # Split into pages
            pages = pdf_text.split('\x0c')
            num_pages = len(pages)
            
            # Convert to markdown
            result = self.md_converter.convert(pdf_path)
            markdown_text = result.text_content
            
            # Add page markers
            for page_num in range(1, num_pages + 1):
                page_marker = f"\n\n[[PAGE_BREAK_{page_num}]]\n\n"
                # Insert markers at appropriate positions
                # Simplified approach - add markers at regular intervals
                if page_num > 1:
                    position = len(markdown_text) * page_num // num_pages
                    markdown_text = (
                        markdown_text[:position] + 
                        page_marker + 
                        markdown_text[position:]
                    )
            
            page_map = [{"page_num": i} for i in range(1, num_pages + 1)]
            return markdown_text, page_map, num_pages
            
        except Exception as e:
            print(f"  Error processing PDF: {e}")
            raise  # Re-raise to be caught by process_file
    
    def _convert_jupyter_notebook(self, notebook_path: str) -> str:
        """Convert Jupyter notebook to markdown."""
        try:
            with open(notebook_path, 'r', encoding='utf-8') as f:
                notebook_data = json.load(f)
            
            markdown_content = [f"# Jupyter Notebook: {os.path.basename(notebook_path)}\n"]
            
            for i, cell in enumerate(notebook_data.get('cells', [])):
                cell_type = cell.get('cell_type', '')
                source = cell.get('source', [])
                
                if isinstance(source, list):
                    source_text = ''.join(source)
                else:
                    source_text = str(source)
                
                if cell_type == 'markdown':
                    markdown_content.append(f"\n## Cell {i+1} (Markdown)\n")
                    markdown_content.append(source_text)
                    markdown_content.append("\n")
                    
                elif cell_type == 'code':
                    markdown_content.append(f"\n## Cell {i+1} (Code)\n")
                    markdown_content.append("```python\n")
                    markdown_content.append(source_text)
                    markdown_content.append("\n```\n")
                    
                    # Add outputs if present
                    outputs = cell.get('outputs', [])
                    if outputs:
                        markdown_content.append("\n**Output:**\n")
                        for output in outputs:
                            if 'text' in output:
                                text_output = output['text']
                                if isinstance(text_output, list):
                                    text_output = ''.join(text_output)
                                markdown_content.append("```\n")
                                markdown_content.append(text_output)
                                markdown_content.append("\n```\n")
            
            return ''.join(markdown_content)
            
        except Exception as e:
            print(f"  Error converting notebook: {e}")
            raise  # Re-raise to be caught by process_file
    
    def _summarize_text(self, doc_type: str, text: str, max_chars: int = 2000) -> Tuple[str, str]:
        """Generate summary and title using OpenAI."""
        snippet = text[:max_chars]
        
        if doc_type == "Lab-code":
            prompt = f"""Analyze this Lab code file:

{snippet}

Return a JSON dictionary with:
1. "Summary": 2-5 line summary of purpose and functionality
2. "Title": Descriptive title (up to 5 words)

Format: {{"Summary": "...", "Title": "..."}}"""
        else:
            prompt = f"""Analyze this {doc_type} document:

{snippet}

Return a JSON dictionary with:
1. "Summary": 2-5 line summary (no institution names)
2. "Title": Descriptive title (1-3 words)

Format: {{"Summary": "...", "Title": "..."}}"""
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a document summarizer."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                timeout=30  # Add timeout
            )
            
            output = response.choices[0].message.content.strip()
            # Clean JSON markers if present
            output = re.sub(r"^```json\s*|\s*```$", "", output.strip())
            
            parsed = json.loads(output)
            return parsed.get("Summary", "No summary available"), parsed.get("Title", "Untitled")
            
        except Exception as e:
            print(f"  Warning: Could not generate summary (API Error): {e}")
            return "Summary unavailable due to API error", "Untitled"
    
    def _determine_doc_type(self, file_name: str, ext: str) -> str:
        """Determine document type based on filename and extension."""
        base_name = os.path.splitext(file_name)[0]
        
        if "Lecture" in base_name:
            return "Lecture"
        elif "Transcript" in base_name:
            return "Lecture Transcript"
        elif "Tutorial" in base_name:
            return "Tutorial"
        elif "Assignment" in base_name:
            return "Assignment"
        elif "Lab" in base_name and ext == ".pdf":
            return "Lab-sheet"
        elif "Lab" in base_name and ext in [".ipynb", ".h", ".cpp"]:
            return "Lab-code"
        elif ext in [".h", ".cpp"]:
            return "Lab-code"
        elif "Book" in base_name:
            return "Book"
        elif ext in [".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"]:
            return "Video"
        else:
            return "Other"
    
    def _chunk_markdown(self, content: str, file_metadata: Dict, 
                        chunk_token_limit: int = 500, 
                        token_overlap: int = 100) -> List[Dict]:
        """Chunk markdown content for embedding."""
        is_pdf = file_metadata.get("extension", "").lower() == ".pdf"
        
        # Split on page markers if PDF
        pages_text = []
        if is_pdf:
            split_pattern = r"\[\[PAGE_BREAK_(\d+)\]\]"
            parts = re.split(split_pattern, content)
            
            # Process splits
            current_page = 1
            for i in range(0, len(parts)):
                if i % 2 == 0 and parts[i].strip():  # Text content
                    pages_text.append((current_page, parts[i]))
                elif i % 2 == 1:  # Page number
                    current_page = int(parts[i]) + 1
        else:
            pages_text.append((1, content))
        
        # Chunk by sentences with overlap
        final_chunks = []
        for page_num, page_text in pages_text:
            sentences = nltk.sent_tokenize(page_text)
            
            current_tokens = []
            current_sentences = []
            
            for sentence in sentences:
                tokens = nltk.word_tokenize(sentence)
                
                if len(current_tokens) + len(tokens) > chunk_token_limit:
                    if current_sentences:
                        chunk_text = " ".join(current_sentences)
                        final_chunks.append({
                            "text": chunk_text,
                            "page": page_num,
                            "metadata": file_metadata
                        })
                        
                        # Handle overlap
                        if token_overlap < len(current_tokens):
                            overlap_tokens = current_tokens[-token_overlap:]
                            overlap_text = " ".join([t for t in overlap_tokens if t])
                            current_tokens = overlap_tokens
                            current_sentences = [overlap_text]
                        else:
                            current_tokens = []
                            current_sentences = []
                
                current_tokens.extend(tokens)
                current_sentences.append(sentence)
            
            # Add remaining content
            if current_sentences:
                chunk_text = " ".join(current_sentences)
                final_chunks.append({
                    "text": chunk_text,
                    "page": page_num,
                    "metadata": file_metadata
                })
        
        return final_chunks
    
    def process_file(self, file_path: str) -> bool:
        """Process a single file through the complete pipeline."""
        file_name = os.path.basename(file_path)
        base_name, ext = os.path.splitext(file_name)
        ext = ext.lower()
        
        try:
            # Check if file needs processing
            file_sig = self._compute_signature(file_path)
            if file_name in self.metadata and self.metadata[file_name].get("signature") == file_sig:
                print(f"[SKIP] No changes: {file_name}")
                return False
            
            # Supported file types
            supported_types = [
                ".pdf", ".h", ".cpp", ".txt", ".pptx", ".docx", ".doc", 
                ".xls", ".xlsx", ".ipynb", ".mp4", ".avi", ".mov", 
                ".mkv", ".wmv", ".flv", ".webm"
            ]
            
            if ext not in supported_types:
                print(f"[SKIP] Unsupported type: {file_name}")
                return False
            
            print(f"[PROCESS] {file_name}")
            
            # Initialize variables
            markdown_text = ""
            page_map = []
            num_pages = "N/A"
            
            # Convert to markdown based on file type
            try:
                if ext == ".pdf":
                    markdown_text, page_map, num_pages = self._convert_pdf_with_pages(file_path)
                    
                elif ext in [".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"]:
                    markdown_text, transcript_only = self._transcribe_video(file_path)
                    
                elif ext == ".ipynb":
                    markdown_text = self._convert_jupyter_notebook(file_path)
                    
                else:
                    # Use MarkItDown for other formats
                    result = self.md_converter.convert(file_path)
                    markdown_text = result.text_content
                    
            except Exception as e:
                error_msg = f"Error converting: {str(e)}"
                print(f"  {error_msg}")
                self._log_error(file_name, "conversion_error", error_msg)
                
                # Create a basic markdown file with error notice
                markdown_text = f"# Error converting {file_name}\n\nError: {str(e)}\n\nFile could not be processed."
            
            # Save markdown file even if there was an error
            output_path = os.path.join(self.output_dir, base_name + ".md")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            
            # Determine document type and generate summary
            doc_type = self._determine_doc_type(file_name, ext)
            
            # Try to generate summary, but don't fail if API has issues
            try:
                summary, title = self._summarize_text(doc_type, markdown_text)
            except Exception as e:
                print(f"  Warning: Summarization failed: {e}")
                summary = "Summary unavailable"
                title = base_name
                self._log_error(file_name, "summary_error", str(e))
            
            # Update metadata
            self.metadata[file_name] = {
                "file_name": file_name,
                "extension": ext,
                "title": title,
                "summary": summary,
                "num_pages": num_pages,
                "signature": file_sig,
                "doc_path": file_path,
                "markdown_path": output_path,
                "page_map": page_map,
                "doc_type": doc_type
            }
            
            # Try to chunk and embed
            try:
                # Chunk and embed
                file_metadata = {
                    "file_name": file_name,
                    "extension": ext,
                    "title": title,
                    "summary": summary,
                    "num_pages": num_pages,
                    "doc_type": doc_type
                }
                
                chunks = self._chunk_markdown(markdown_text, file_metadata)
                
                # Prepare for ChromaDB
                ids, documents, metadatas = [], [], []
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{file_name}_page{chunk['page']}_chunk{i}"
                    ids.append(chunk_id)
                    documents.append(chunk["text"])
                    metadatas.append({
                        "source_file": file_name,
                        "page": chunk["page"],
                        **chunk["metadata"]
                    })
                
                # Add to ChromaDB
                if ids:
                    self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
                    print(f"  Added {len(ids)} chunks to ChromaDB")
                    
            except Exception as e:
                error_msg = f"Error adding to ChromaDB: {str(e)}"
                print(f"  Warning: {error_msg}")
                self._log_error(file_name, "chromadb_error", error_msg)
                # Continue processing other files even if ChromaDB fails
            
            return True
            
        except Exception as e:
            # Catch any unexpected errors
            error_msg = f"Unexpected error processing file: {str(e)}\n{traceback.format_exc()}"
            print(f"  [ERROR] {file_name}: {str(e)}")
            self._log_error(file_name, "unexpected_error", error_msg)
            return False
    
    def process_directory(self):
        """Process all files in the input directory."""
        if not os.path.exists(self.input_dir):
            print(f"Error: Input directory does not exist: {self.input_dir}")
            return
        
        print(f"\nProcessing module: {self.module}")
        print(f"Input directory: {self.input_dir}")
        print(f"Output directory: {self.output_dir}")
        print(f"ChromaDB directory: {self.chroma_dir}\n")
        
        # Collect all files
        files_processed = 0
        files_skipped = 0
        files_errored = 0
        
        for root, dirs, files in os.walk(self.input_dir):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                try:
                    if self.process_file(file_path):
                        files_processed += 1
                    else:
                        files_skipped += 1
                except Exception as e:
                    files_errored += 1
                    print(f"[ERROR] Failed to process {file_name}: {e}")
                    self._log_error(file_name, "process_error", str(e))
        
        # Save metadata and errors
        self._save_metadata()
        self._save_errors()
        
        # Print summary
        print(f"\n{'='*50}")
        print(f"Processing complete for module: {self.module}")
        print(f"Files processed: {files_processed}")
        print(f"Files skipped: {files_skipped}")
        print(f"Files with errors: {files_errored}")
        
        try:
            print(f"Total documents in ChromaDB: {self.collection.count()}")
        except:
            print(f"Total documents in ChromaDB: Unable to count")
        
        if self.errors:
            print(f"\nFiles with errors (see {self.error_log_path}):")
            for file_name in self.errors:
                print(f"  - {file_name}: {self.errors[file_name]['error_type']}")
        
        print(f"{'='*50}\n")
    
    def verify_chromadb(self):
        """Verify ChromaDB contents."""
        try:
            print(f"\nVerifying ChromaDB for module: {self.module}")
            print(f"Collection: {self.module}")
            print(f"Total documents: {self.collection.count()}")
            
            # Sample some documents
            sample = self.collection.get(limit=5)
            if sample['ids']:
                print(f"\nSample documents:")
                for i, doc_id in enumerate(sample['ids'][:3]):
                    print(f"  - {doc_id}")
                    if sample['metadatas'][i]:
                        print(f"    Source: {sample['metadatas'][i].get('source_file', 'Unknown')}")
        except Exception as e:
            print(f"Error verifying ChromaDB: {e}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Process documents for a module: convert to markdown, chunk, embed, and store in ChromaDB"
    )
    parser.add_argument(
        "module",
        type=str,
        help="Module code (e.g., PSY555, CMP511)"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify ChromaDB contents without processing"
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Retry processing files that previously had errors"
    )
    
    args = parser.parse_args()
    
    try:
        processor = DocumentProcessor(args.module)
        
        if args.verify_only:
            processor.verify_chromadb()
        elif args.retry_errors:
            # Clear errors for retry
            if processor.errors:
                print(f"Retrying {len(processor.errors)} files with previous errors...")
                processor.errors = {}
                processor._save_errors()
            processor.process_directory()
            processor.verify_chromadb()
        else:
            processor.process_directory()
            processor.verify_chromadb()
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()