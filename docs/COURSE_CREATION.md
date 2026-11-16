# Course Creation Guide

This guide explains how to add a new course to LEA.

## Overview

Adding a course requires four main steps:
1. Prepare course materials
2. Describe the course (course profile: name and programming language)
3. Generate Knowledge Component (KC) model
4. Build RAG library

A course appears in LEA as soon as it has a folder under `data/kc_models/`. Nothing in the code needs to be edited to add one.

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
mkdir -p data/course_profiles
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

## Step 2: Describe the Course (Programming Language)

LEA writes quiz questions to suit the course. Whether a course teaches programming, and in which
language, is set in a small course profile: `data/course_profiles/YOUR_COURSE_CODE.json`.

```json
{
  "code": "YOUR_COURSE_CODE",
  "name": "Your Course Name",
  "programming_language": "cpp",
  "allow_code_questions": true
}
```

| Field | Meaning |
|-------|---------|
| `code` | The course code, the same as the folder names under `data/`. |
| `name` | The course name, used in prompts, course descriptions and the KC model generator. |
| `programming_language` | A short language key such as `"python"`, `"cpp"` (C++), `"java"`, `"csharp"`, `"javascript"`, `"r"` or `"sql"`, or `null` if the course has no programming. |
| `allow_code_questions` | `true` or `false`. Set `false` to switch code questions off for a course that does have a language. |

**A course with no programming (humanities, mathematics, design and so on).** Set
`"programming_language": null`. Quizzes for that course then never contain code questions, and the
question prompts tell the model not to include code.

**A C++ course.** Set `"programming_language": "cpp"`. Code questions are then written in C++
and shown in `cpp` code blocks; the quiz prompts do not mention Python.

**Another language.** Any short key works; it is shown with a capital letter (for example
`"kotlin"` becomes Kotlin) and the prompts ask for code in that language.

**No profile file.** A course with no profile is treated as having no programming language, so it
never gets code questions by accident. `data/course_profiles/DEMO101.json` (Python) is the example.

## Step 3: Create KC Model Template

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

The generator reads the course name from the course profile (Step 2), so create the profile first.

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

## Step 4: Generate RAG Library

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

## Step 5: Test the Course

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

### Course Names

The course name is the `name` field of the course profile, `data/course_profiles/YOUR_COURSE_CODE.json` (Step 2).
Change it there; no code needs editing.

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

## Adding a new course (COURSE123)

```bash
# 1. Create directories
mkdir -p data/org_docs/COURSE123 data/course_profiles

# 2. Add course files
# (Copy PDFs, slides, code, etc. to data/org_docs/COURSE123/)

# 3. Create the course profile: data/course_profiles/COURSE123.json
#    {"code": "COURSE123", "name": "Your Course Name", "programming_language": null, "allow_code_questions": false}
#    Use null for a course without programming, or e.g. "cpp" / "python" for a programming course.

# 4. Create the template
# (Create COURSE123.xlsx in data_foundation/, as in Step 3)

# 5. Generate the KC model
cd data_foundation
python kc_model_generator.py COURSE123
# Review COURSE123_Improved_KC_Model.xlsx and save it as COURSE123_Improved_KC_Model_Updated.xlsx
python create_kc_model.py COURSE123

# 6. Generate the RAG library
cd ..
python data_foundation/rag_library_creation.py COURSE123

# 7. Test
streamlit run src/ui/streamlit_app.py
```

The course appears in the app once `data/kc_models/COURSE123/` exists.

## Need Help?

- Use the synthetic DEMO101 course as the worked example
- Review error logs in console output
- Verify file permissions and paths
- Ensure OpenAI API key has credits