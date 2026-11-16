# LEA - Learning Engagement Assistant

An adaptive, scalable, tri-modal AI tutoring system designed to personalize instruction in STEM education.

## Overview

LEA (Learning Engagement Assistant) is a proof-of-concept agentic AI system that provides personalized academic support through three learning modes:

- **Chat Mode**: Open-ended Q&A with course-grounded responses
- **Tutor Mode**: Guided instruction with adaptive scaffolding
- **Quiz Mode**: Dynamic assessment with difficulty calibration

## Key Features

- **Adaptive Scaffolding**: Real-time adjustment based on cognitive load and learner performance
- **Knowledge Component Modeling**: Hierarchical learning objectives with mastery tracking
- **RAG-Based Content**: Retrieval-Augmented Generation grounded in course materials
- **Multi-Modal Learning**: Flexible interaction styles for diverse learner needs
- **Scalable Architecture**: Supports multiple courses with automated content generation

## Demo Course

LEA ships with one synthetic course, DEMO101 (Introduction to AI/ML). Counted from
`data/kc_models/DEMO101/kc_model_DEMO101.json` and the files under `data/`:

- 3 weeks in the knowledge-component (KC) model (Introduction to AI, Machine Learning Basics, Neural Networks)
- 9 learning objectives (3 per week)
- 32 granular objectives, the KCs that mastery is tracked against
- 2 example lecture documents (weeks 1 and 2 only) in a pre-generated vector store of 2 chunks;
  week 3 has objectives but no materials
- a course profile (`data/course_profiles/DEMO101.json`) that sets the programming language
  (Python) used for code questions

## Data Availability

Institutional course materials, KC models, RAG databases and evaluation data for the real courses
used in the research are **not released**. Only the synthetic course DEMO101 is provided. To use
LEA with your own course, follow [Course Creation](docs/COURSE_CREATION.md).

## Quick Start

### Prerequisites

- Python 3.11+
- Redis (for session management)
- OpenAI API key

### Installation

```bash
git clone https://github.com/tep00018/LEA.git
cd LEA

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your credentials
```

### Running LEA

```bash
# Start Redis
redis-server

# Run the application
streamlit run src/ui/streamlit_app.py
```

Visit http://localhost:8501

## Documentation

- [Setup Guide](docs/SETUP.md) - Installation instructions
- [Architecture](docs/ARCHITECTURE.md) - System design
- [Startup Guide](docs/STARTUP.md) - Starting and running the UI
- [Course Creation](docs/COURSE_CREATION.md) - Adding new courses

## Research Context

Developed as part of a dissertation on adaptive intelligent tutoring systems (see Citation below).

## License

Apache 2.0 License - see LICENSE file

## Citation

Conference paper: *Learning Engagement Assistant (LEA): A Multi-Agent AI Framework for
Adaptive and Personalized Learning with Simulated Student Agents*, ICAART 2026,
DOI [10.5220/0014418900004052](https://doi.org/10.5220/0014418900004052).

Journal article (SN Computer Science): *[PAPER TITLE - TO BE ADDED]*, SN Computer Science,
[YEAR, VOLUME, PAGES - TO BE ADDED], DOI [TO BE ADDED].

Dissertation:

```bibtex
@mastersthesis{rumble2025,
  title={LEA: An Adaptive Agentic AI Framework for Personalized STEM Education},
  author={Rumble, Teri},
  year={2025},
  school={Abertay University}
}
```
