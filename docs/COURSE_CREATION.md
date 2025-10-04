# Course Creation Guide

This guide explains how to add a new course to LEA.

## Overview

Adding a course requires three main steps:
1. Prepare course materials
2. Generate Knowledge Component (KC) model
3. Build RAG library

## Prerequisites

- Course materials (PDFs, DOCX, videos, code, etc.)
- OpenAI API key configured in `.env`
- Redis running

## Step 1: Organize Course Materials

### Create Directory Structure

```bash
cd LEA
mkdir -p data/org_docs/YOUR_COURSE_CODE
mkdir -p data/kc_models/YOUR_COURSE_CODE
```

### File Naming Convention

Use this format for all materials:
```
Week{N}-{Type}{Letter}-{Description}.{ext}
```

Examples:
- `Week1-LectureA-Introduction.pdf`
- `Week2-LabA-PythonBasics.ipynb`
- `Week3-VideoA-DeepLearning.mp4`
- `Week5-TutorialB-Optimization.docx`

### Supported File Types

- **Documents**: PDF, DOCX, TXT, Markdown
- **Code**: .py, .ipynb, .cpp, .java
- **Videos**: .mp4, .avi, .mov, .mkv
- **Presentations**: .pptx

Place all files in `data/org_docs/YOUR_COURSE_CODE/`

## Step 2: Create KC Model Template

### Create Excel Template

Create `data_foundation/YOUR_COURSE_CODE.xlsx` with two sheets:

**Sheet 1: Template**

| Week | Week Description | Learning Objectives | Supporting Materials |
|------|------------------|---------------------|---------------------|
| 1 | Introduction | 1. Objective one<br>2. Objective two | data/md_docs/YOUR_COURSE_CODE/Week1- |
| 2 | Core Concepts | 1. Objective three<br>2. Objective four | data/md_docs/YOUR_COURSE_CODE/Week2- |

**Sheet 2: Partial_Example**

Copy the structure from `DEMO101.xlsx` Partial_Example sheet or use this minimal example:

| KC# | Module | Module Name | Week # | Week Name | LO# | Learning Objective Name | GO# | Granular Objective Name | cognitive_level |
|-----|--------|-------------|---------|-----------|-----|-------------------------|-----|-------------------------|-----------------|
| KC_W01_L01_001 | YOUR_CODE | Course Name | W01 | Week 1 | L01 | LO Name | 001 | GO Name | Knowledge |

### Generate KC Model

```bash
cd data_foundation
python kc_model_generator.py YOUR_COURSE_CODE
```

This creates:
- `YOUR_COURSE_CODE_Improved_KC_Model.xlsx`

### Review and Edit

1. Open the generated Excel file
2. Review granular objectives for accuracy
3. Adjust cognitive levels and difficulty if needed
4. Save as `YOUR_COURSE_CODE_Improved_KC_Model_Updated.xlsx`

### Convert to JSON

```bash
python create_kc_model.py YOUR_COURSE_CODE
```

This creates:
- `data/kc_models/YOUR_COURSE_CODE/kc_model_YOUR_COURSE_CODE.json`

## Step 3: Generate RAG Library

### Process Course Materials

```bash
cd ..
python data_foundation/rag_library_creation.py YOUR_COURSE_CODE
```

This will:
1. Convert all files to markdown
2. Extract text from PDFs, videos, etc.
3. Chunk content into semantic segments
4. Generate embeddings
5. Store in ChromaDB

Output:
- `data/md_docs/YOUR_COURSE_CODE/` - Markdown conversions
- `data/chroma_data/YOUR_COURSE_CODE/` - Vector database

### Verify RAG Library

```bash
python data_foundation/verify_rag_content.py YOUR_COURSE_CODE
```

## Step 4: Test the Course

### Start LEA

```bash
streamlit run src/ui/streamlit_app.py
```

### Test Each Mode

1. **Register/Login** with a test account
2. **Select** your new course from the dropdown
3. **Chat Mode**: Ask a general question about Week 1 content
4. **Tutor Mode**: Start tutoring on Week 1, LO 1
5. **Quiz Mode**: Take a quiz on Week 1

### Troubleshooting

**KC Model Not Loading**
```bash
ls data/kc_models/YOUR_COURSE_CODE/
# Should show kc_model_YOUR_COURSE_CODE.json
```

**RAG Retrieval Empty**
```bash
python data_foundation/verify_rag_content.py YOUR_COURSE_CODE
# Should show document count > 0
```

**Missing Course in Dropdown**
- Verify JSON file exists in correct location
- Check file naming matches course code
- Restart Streamlit

## Best Practices

### Learning Objectives

- Be specific and measurable
- Use action verbs (understand, apply, analyze)
- Align with Bloom's taxonomy
- Limit to 3-5 per week

### Course Materials

- Include varied content types
- Provide worked examples
- Include code samples when relevant
- Keep files reasonably sized (<50MB each)

### KC Model Review

- Verify cognitive levels are appropriate
- Check mastery thresholds (0.6-0.9 range)
- Ensure granular objectives are distinct
- Validate prerequisite relationships

## Advanced Configuration

### Custom Course Names

Edit `data_foundation/kc_model_generator.py`:

```python
course_names = {
    "CMP511": "Machine Learning and AI",
    "YOUR_CODE": "Your Course Name",
}
```

### Adjust Mastery Thresholds

Edit generated KC model JSON:
```json
{
  "mastery_threshold": 0.75,  // Adjust per objective
  "difficulty": 3              // 1-5 scale
}
```

### Custom Scaffolding Rules

Modify `src/core/scaffolding_engine.py` for course-specific logic.

## Example: Adding PSY555

```bash
# 1. Create directories
mkdir -p data/org_docs/PSY555

# 2. Add course files
# (Copy PDFs, etc. to data/org_docs/PSY555/)

# 3. Create template
# (Create PSY555.xlsx in data_foundation/)

# 4. Generate KC model
cd data_foundation
python kc_model_generator.py PSY555
# Review PSY555_Improved_KC_Model.xlsx
python create_kc_model.py PSY555

# 5. Generate RAG
cd ..
python data_foundation/rag_library_creation.py PSY555

# 6. Test
streamlit run src/ui/streamlit_app.py
```

## Need Help?

- Check existing courses (DEMO101, CMP511) as examples
- Review error logs in console output
- Verify file permissions and paths
- Ensure OpenAI API key has credits