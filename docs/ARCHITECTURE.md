# LEA System Architecture

## Overview

LEA employs a modular, multi-agent architecture that integrates course-specific knowledge, real-time learner assessment, and adaptive content generation to deliver personalized instruction.

## Core Components

### 1. Data Foundation

**Knowledge Component (KC) Model**
- Hierarchical structure: Week → Learning Objective → Granular Objective
- Stores difficulty levels, cognitive taxonomy, mastery thresholds
- Enables targeted skill assessment and adaptive sequencing
- JSON format for programmatic access

**RAG Library (Retrieval-Augmented Generation)**
- Vector database (ChromaDB) storing embedded course content
- Enables semantic search over lectures, labs, and materials
- Provides context-grounded responses to student queries
- Supports multiple document types (PDF, DOCX, videos, code)

### 2. Agentic Environment

**Agent Orchestrator**
- Central coordination layer assessing learner state
- Monitors cognitive load, ZPD alignment, motivation
- Determines scaffolding strategy and content difficulty
- Routes requests to appropriate content generation agents

**Scaffolding Engine**
- Maps learner state to pedagogical interventions
- Four scaffold types: Conceptual, Procedural, Strategic, Metacognitive
- Implements fading logic based on performance trends
- Adjusts support intensity across five levels

**Mastery Tracker**
- Maintains persistent learner progress across sessions
- Tracks mastery at GO, LO, and week levels
- Uses weighted moving averages for stability
- Informs content selection and difficulty adaptation

### 3. Content Generation Agents

**Chat Agent**
- General Q&A using RAG retrieval
- No mastery tracking or scaffolding
- Provides quick answers grounded in course materials

**Tutor Agent**
- Guided instruction through learning objectives
- Multi-turn conversations with adaptive scaffolding
- Generates follow-up questions based on understanding
- Provides worked examples when appropriate

**Quiz Agent**
- Dynamic question generation per granular objective
- Multiple question types: MC, T/F, Fill-in-blank, Open-ended
- Difficulty calibration based on learner profile
- Immediate feedback with explanations

### 4. Model Context Protocol (MCP)

**Standardized Communication Layer**
- Abstracts tool integration complexity
- Provides uniform interface for internal/external services
- Enables dynamic tool discovery and session management
- Supports extensibility without code changes

**Current MCP Tools**
- RAG retrieval
- KC model lookup
- Mastery summary and updates
- Academic calendar
- YouTube worked examples
- Web search (DuckDuckGo)
- Weather service (example external integration)

### 5. Memory Management

**Short-term Memory (Redis)**
- Session context and conversation history
- Recent learner interactions (24hr TTL)
- Enables multi-turn coherence

**Long-term Memory (Redis)**
- Consolidated session summaries (90-day TTL)
- Learning patterns and preferences
- Supports cross-session personalization

### 6. User Interface (Streamlit)

**Command Center**
- Course and week selection
- Mode switching (Chat/Tutor/Quiz)
- Progress visualization
- Mastery badges

**Adaptive Interface**
- Reduces extraneous cognitive load
- Progressive disclosure of complexity
- Clear visual hierarchy
- Responsive design

## Data Flow

### Student Interaction Cycle

1. **Input Reception**: User submits query/response
2. **Context Retrieval**: Load conversation history and learner profile
3. **State Assessment**: Calculate cognitive load, ZPD, motivation
4. **Scaffolding Decision**: Determine support type and intensity
5. **Content Generation**: Create adaptive response using RAG + KC model
6. **Mastery Update**: Assess understanding and update progress
7. **Response Delivery**: Present content with appropriate scaffolding
8. **Memory Storage**: Persist interaction for future sessions

## Scalability Design

**Course-Agnostic Architecture**
- Automated KC model generation from course materials
- Template-based RAG library creation
- Minimal manual configuration per course

**Modular Components**
- Independent agents can be updated without system changes
- MCP enables adding new tools without code modification
- Clear separation of concerns across layers

## Technical Stack

- **Backend**: Python 3.11+
- **LLM**: OpenAI GPT-4 / GPT-4o-mini
- **Vector DB**: ChromaDB
- **Session Store**: Redis
- **UI Framework**: Streamlit
- **Embedding Model**: text-embedding-3-small
- **Protocol**: Model Context Protocol (MCP)

## Security Considerations

- Environment-based credential management
- User authentication for session isolation
- Redis-backed session management
- No persistent storage of API keys
- Audit logging for instructional decisions

## Future Enhancements

- Multi-LLM support (local models, Claude, etc.)
- Advanced mastery models (Deep Knowledge Tracing)
- Collaborative learning features
- Instructor dashboard and analytics
- Docker containerization for deployment