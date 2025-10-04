```markdown
# 📚 RAG Library & KC Model Generation Guide

This repository contains two core workflows:

1. **RAG Library Creation** – Transform course materials into a structured knowledge base for Retrieval-Augmented Generation (RAG) applications.
2. **Knowledge Component (KC) Model Generation** – Convert course learning objectives into structured KC models for intelligent tutoring systems.

---

## 1️⃣ RAG Library Creation

### Purpose
Create a document processing pipeline that ingests, converts, and indexes course-specific materials into a ChromaDB-backed knowledge base.

### Installation
Place the script in the project root:
```bash
rag_library_creation.py
```

### Directory Setup
```bash
mkdir -p data/{org_docs,md_docs,chroma_data,metadata}
mkdir -p data/org_docs/MODULE_CODE
mkdir -p data/md_docs/MODULE_CODE
mkdir -p data/chroma_data/MODULE_CODE
```

### Document Naming Convention
```
Week<Number>-<Type><A/B/C>-<OptionalDescription>.<ext>
# Example:
Week1-LectureA-Introduction.pptx
```

### Supported Formats
| Type              | Extensions                                      | Processing Method              |
|-------------------|-------------------------------------------------|---------------------------------|
| PDF               | `.pdf`                                          | PDFMiner (page-preserving)      |
| Video             | `.mp4`, `.avi`, `.mov`, `.mkv`, `.wmv`, `.flv`, `.webm` | Whisper ASR transcription      |
| Jupyter Notebook  | `.ipynb`                                         | Native JSON parsing             |
| Word              | `.docx`, `.doc`                                  | MarkItDown conversion           |
| PowerPoint        | `.pptx`                                          | MarkItDown conversion           |
| Excel             | `.xlsx`, `.xls`                                  | MarkItDown conversion           |
| Source Code       | `.py`, `.cpp`, `.h`                              | Direct text processing          |
| Plain Text        | `.txt`                                           | Direct text processing          |

### Running the Pipeline
```bash
python rag_library_creation.py MODULE_CODE
# Verify ChromaDB without processing:
python rag_library_creation.py MODULE_CODE --verify-only
```

### Output Structure
```
data/
├ org_docs/{module}/           # Original uploaded files
├ org_docs_archive/{module}/   # Unconvertible files
├ md_docs/{module}/            # Markdown-converted files
├ signatures/{module}/         # File signatures
├ metadata/{module}/           # Processing metadata
├ chroma_data/{module}/        # ChromaDB collection
```

**Metadata Example (`doc_metadata_{module}.json`):**
```json
{
  "filename.pdf": {
    "file_name": "filename.pdf",
    "extension": ".pdf",
    "title": "Generated Title",
    "summary": "Document summary...",
    "num_pages": 10,
    "signature": "md5_hash",
    "doc_path": "data/org_docs/MODULE/filename.pdf",
    "markdown_path": "data/md_docs/MODULE/filename.md",
    "doc_type": "Lecture"
  }
}
```

---

## 2️⃣ Knowledge Component (KC) Model Generation

### Purpose
Automate the transformation of course learning objectives into granular, structured KC models for adaptive learning systems.

### Workflow Overview
1. **Fill Excel Template** – Define weekly structure, learning objectives, and supporting material paths.
2. **Automated KC Generation** – AI decomposes objectives into granular components.
3. **Manual Review** – Experts refine and validate the generated model.
4. **JSON Conversion** – Final model is exported for LEA integration.

---

### Step 1: Fill Excel Template
- **File Name:** `[COURSE_CODE].xlsx`
- **Columns:**
  - `Week` – Numeric week ID
  - `Week Description` – Concise title
  - `Learning Objectives` – Numbered list per cell
  - `Supporting Materials` – Path prefix to RAG Library files

---

### Step 2: Automated KC Generation
```bash
python kc_model_generator.py COURSE_CODE
```
- **Output:** `[COURSE_CODE]_Improved_KC_Model.xlsx`
- Includes:
  - Concept names
  - Bloom’s taxonomy levels
  - Mastery thresholds
  - Cross-week dependencies
  - Statistical summaries

---

### Step 3: Manual Review
- Validate accuracy, relevance, and pedagogy.
- Adjust:
  - Objective clarity
  - Cognitive levels
  - Mastery thresholds
  - Prerequisite links
- **Save As:** `[COURSE_CODE]_Improved_KC_Model_Updated.xlsx`

---

### Step 4: JSON Model Generation
```bash
python create_kc_model.py COURSE_CODE
```
- **Output Directory:** `data/kc_models/[COURSE_CODE]/`
- **Files:**
  - `kc_model_[COURSE_CODE].json` – Full KC model
- Includes:
  - Objective hierarchies
  - Assessment strategies
  - Navigation structures
  - QA statistics

---

## 📂 File Location Rules
- All input/output files must be in the script execution directory.
- No relative/absolute path arguments supported.

---

## 📝 Summary
- **RAG Library Creation** → Prepares and indexes course materials for retrieval.
- **KC Model Generation** → Builds structured, adaptive learning models from course objectives.
```
