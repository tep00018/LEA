# LEA - Learning Environment Assistant

An adaptive, scalable, tri-modal AI tutoring system designed to personalize instruction in STEM education.

## Overview

LEA (Learning Environment Assistant) is a proof-of-concept agentic AI system that provides personalized academic support through three learning modes:

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

Includes DEMO101 (Introduction to AI/ML) demonstrating:
- 3 weeks of content
- 9 learning objectives
- 32 granular knowledge components
- Pre-generated RAG library

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

Developed as part of a dissertation on adaptive intelligent tutoring systems at Abertay University.

## License

Apache 2.0 License - see LICENSE file

## Citation

```bibtex
@mastersthesis{rumble2025,
  title={LEA: An Adaptive Agentic AI Framework for Personalized STEM Education},
  author={Rumble, Teri},
  year={2025},
  school={Abertay University}
}
```