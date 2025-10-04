# src/core/academic_calendar.py

"""
Enhanced Academic Calendar System for LEA Tutor
Supports multiple courses and academic events
"""

from datetime import datetime, timedelta
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

class EventType(Enum):
    """Types of academic events"""
    LECTURE = "lecture"
    TUTORIAL = "tutorial"
    ASSIGNMENT_DUE = "assignment_due"
    EXAM = "exam"
    PROJECT_DUE = "project_due"
    HOLIDAY = "holiday"
    ASSESSMENT_WEEK = "assessment_week"
    TERM_START = "term_start"
    TERM_END = "term_end"
    NO_CLASSES = "no_classes"

@dataclass
class AcademicEvent:
    """Represents a single academic event"""
    event_id: str
    event_type: EventType
    title: str
    description: str
    start_date: datetime
    end_date: datetime
    course: Optional[str] = None
    week: Optional[int] = None
    priority: int = 1  # 1=high, 2=medium, 3=low

@dataclass
class AcademicWeek:
    """Represents an academic week with its events"""
    week_number: int
    start_date: datetime
    end_date: datetime
    week_type: str  # "teaching", "assessment", "holiday"
    events: List[AcademicEvent]

class AcademicCalendar:
    """
    Enhanced academic calendar that supports multiple institutions and courses
    """
    
    def __init__(self, institution_config: Dict[str, Any]):
        """
        Initialize calendar with institution configuration
        
        Args:
            institution_config: Configuration containing term dates, courses, etc.
        """
        self.institution_name = institution_config.get("name", "Unknown Institution")
        self.term_config = institution_config.get("term", {})
        self.courses_config = institution_config.get("courses", {})
        
        # Parse term dates
        self.term_start = datetime.fromisoformat(self.term_config.get("start_date"))
        self.term_end = datetime.fromisoformat(self.term_config.get("end_date"))
        self.total_weeks = self.term_config.get("total_weeks", 14)
        self.teaching_weeks = self.term_config.get("teaching_weeks", 10)
        
        # Build academic weeks and events
        self.academic_weeks = self._build_academic_weeks()
        self.all_events = self._build_all_events()
        
        print(f"DEBUG: Academic calendar initialized for {self.institution_name}")
        print(f"DEBUG: Term: {self.term_start.date()} to {self.term_end.date()}")
    
    def _build_academic_weeks(self) -> List[AcademicWeek]:
        """Build all academic weeks for the term"""
        weeks = []
        
        for i in range(self.total_weeks):
            week_num = i + 1
            week_start = self.term_start + timedelta(days=7 * i)
            week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            
            # Determine week type
            if week_num <= self.teaching_weeks:
                week_type = "teaching"
            else:
                week_type = "assessment"
            
            week = AcademicWeek(
                week_number=week_num,
                start_date=week_start,
                end_date=week_end,
                week_type=week_type,
                events=[]
            )
            weeks.append(week)
        
        return weeks
    
    def _build_all_events(self) -> List[AcademicEvent]:
        """Build all academic events from configuration"""
        events = []
        
        # Add term-level events
        events.extend(self._build_term_events())
        
        # Add course-specific events
        for course_name, course_config in self.courses_config.items():
            events.extend(self._build_course_events(course_name, course_config))
        
        return sorted(events, key=lambda x: x.start_date)
    
    def _build_term_events(self) -> List[AcademicEvent]:
        """Build term-level events"""
        events = []
        
        # Term start
        events.append(AcademicEvent(
            event_id="term_start",
            event_type=EventType.TERM_START,
            title="Term Begins",
            description="Start of academic term",
            start_date=self.term_start,
            end_date=self.term_start,
            priority=1
        ))
        
        # Term end
        events.append(AcademicEvent(
            event_id="term_end",
            event_type=EventType.TERM_END,
            title="Term Ends",
            description="End of academic term",
            start_date=self.term_end,
            end_date=self.term_end,
            priority=1
        ))
        
        # Assessment weeks
        for week_num in range(self.teaching_weeks + 1, self.total_weeks + 1):
            week_start = self.term_start + timedelta(days=7 * (week_num - 1))
            events.append(AcademicEvent(
                event_id=f"assessment_week_{week_num}",
                event_type=EventType.ASSESSMENT_WEEK,
                title=f"Assessment Week {week_num}",
                description="Assessment and examination period",
                start_date=week_start,
                end_date=week_start + timedelta(days=6),
                week=week_num,
                priority=1
            ))
        
        # Add holidays if configured
        holidays = self.term_config.get("holidays", [])
        for holiday in holidays:
            events.append(AcademicEvent(
                event_id=holiday["id"],
                event_type=EventType.HOLIDAY,
                title=holiday["title"],
                description=holiday.get("description", ""),
                start_date=datetime.fromisoformat(holiday["start_date"]),
                end_date=datetime.fromisoformat(holiday["end_date"]),
                priority=2
            ))
        
        return events
    
    def _build_course_events(self, course_name: str, course_config: Dict) -> List[AcademicEvent]:
        """Build events for a specific course"""
        events = []
        
        # Add assignments
        assignments = course_config.get("assignments", [])
        for assignment in assignments:
            due_date = datetime.fromisoformat(assignment["due_date"])
            events.append(AcademicEvent(
                event_id=f"{course_name}_{assignment['id']}",
                event_type=EventType.ASSIGNMENT_DUE,
                title=f"{course_name}: {assignment['title']}",
                description=assignment.get("description", ""),
                start_date=due_date,
                end_date=due_date,
                course=course_name,
                week=self._get_week_number(due_date),
                priority=1
            ))
        
        # Add exams
        exams = course_config.get("exams", [])
        for exam in exams:
            exam_date = datetime.fromisoformat(exam["date"])
            events.append(AcademicEvent(
                event_id=f"{course_name}_{exam['id']}",
                event_type=EventType.EXAM,
                title=f"{course_name}: {exam['title']}",
                description=exam.get("description", ""),
                start_date=exam_date,
                end_date=exam_date,
                course=course_name,
                week=self._get_week_number(exam_date),
                priority=1
            ))
        
        # Add projects
        projects = course_config.get("projects", [])
        for project in projects:
            due_date = datetime.fromisoformat(project["due_date"])
            events.append(AcademicEvent(
                event_id=f"{course_name}_{project['id']}",
                event_type=EventType.PROJECT_DUE,
                title=f"{course_name}: {project['title']}",
                description=project.get("description", ""),
                start_date=due_date,
                end_date=due_date,
                course=course_name,
                week=self._get_week_number(due_date),
                priority=1
            ))
        
        return events
    
    def _get_week_number(self, date: datetime) -> Optional[int]:
        """Get academic week number for a given date"""
        if date < self.term_start or date > self.term_end:
            return None
        
        for week in self.academic_weeks:
            if week.start_date <= date <= week.end_date:
                return week.week_number
        
        return None
    
    def get_current_academic_info(self) -> Dict[str, Any]:
        """
        Get comprehensive current academic information
        Enhanced version of your original function
        """
        now = datetime.now()
        
        # Basic time information
        result = {
            "institution": self.institution_name,
            "current_datetime": now.isoformat(),
            "month": now.strftime("%B"),
            "date": now.strftime("%d"),
            "day_of_week": now.strftime("%A"),
            "time": now.strftime("%H:%M:%S"),
            "academic_week": None,
            "week_type": None,
            "event": "Term not active",
            "current_events": [],
            "upcoming_events": [],
            "recent_events": []
        }
        
        # Determine current academic week
        if self.term_start <= now <= self.term_end:
            for week in self.academic_weeks:
                if week.start_date <= now <= week.end_date:
                    result["academic_week"] = week.week_number
                    result["week_type"] = week.week_type
                    result["event"] = f"Academic Week {week.week_number} ({week.week_type.title()})"
                    break
        elif now < self.term_start:
            result["event"] = "Term has not started yet"
        else:
            result["event"] = "Term ended"
        
        # Get current, upcoming, and recent events
        result["current_events"] = self._get_current_events(now)
        result["upcoming_events"] = self._get_upcoming_events(now)
        result["recent_events"] = self._get_recent_events(now)
        
        return result
    
    def get_course_specific_info(self, course_name: str, username: str = None) -> Dict[str, Any]:
        """
        Get academic information specific to a course and optionally a student
        """
        now = datetime.now()
        
        # Get general academic info
        info = self.get_current_academic_info()
        
        # Add course-specific information
        course_events = [event for event in self.all_events if event.course == course_name]
        
        info.update({
            "course": course_name,
            "course_current_events": [self._event_to_dict(e) for e in course_events if self._is_current_event(e, now)],
            "course_upcoming_events": [self._event_to_dict(e) for e in course_events if self._is_upcoming_event(e, now)][:5],
            "course_assignments_due_soon": self._get_assignments_due_soon(course_name, now),
            "course_week_context": self._get_week_context(course_name, info.get("academic_week"))
        })
        
        return info
    
    def _get_current_events(self, now: datetime) -> List[Dict]:
        """Get events happening today"""
        current = []
        for event in self.all_events:
            if event.start_date.date() <= now.date() <= event.end_date.date():
                current.append(self._event_to_dict(event))
        return sorted(current, key=lambda x: x["priority"])
    
    def _get_upcoming_events(self, now: datetime, days_ahead: int = 7) -> List[Dict]:
        """Get events in the next N days"""
        upcoming = []
        cutoff = now + timedelta(days=days_ahead)
        
        for event in self.all_events:
            if now < event.start_date <= cutoff:
                upcoming.append(self._event_to_dict(event))
        
        return sorted(upcoming, key=lambda x: x["start_date"])[:10]
    
    def _get_recent_events(self, now: datetime, days_back: int = 3) -> List[Dict]:
        """Get recent events from the past N days"""
        recent = []
        cutoff = now - timedelta(days=days_back)
        
        for event in self.all_events:
            if cutoff <= event.end_date < now:
                recent.append(self._event_to_dict(event))
        
        return sorted(recent, key=lambda x: x["end_date"], reverse=True)[:5]
    
    def _get_assignments_due_soon(self, course_name: str, now: datetime, days_ahead: int = 14) -> List[Dict]:
        """Get assignments due in the next N days for a specific course"""
        due_soon = []
        cutoff = now + timedelta(days=days_ahead)
        
        for event in self.all_events:
            if (event.course == course_name and 
                event.event_type == EventType.ASSIGNMENT_DUE and
                now <= event.start_date <= cutoff):
                due_soon.append(self._event_to_dict(event))
        
        return sorted(due_soon, key=lambda x: x["start_date"])
    
    def _get_week_context(self, course_name: str, week_number: Optional[int]) -> str:
        """Get contextual information about the current week for a course"""
        if not week_number:
            return "Not currently in academic term"
        
        if week_number <= self.teaching_weeks:
            return f"Teaching week {week_number} of {self.teaching_weeks}"
        else:
            return f"Assessment week {week_number - self.teaching_weeks} of {self.total_weeks - self.teaching_weeks}"
    
    def _is_current_event(self, event: AcademicEvent, now: datetime) -> bool:
        """Check if event is currently happening"""
        return event.start_date <= now <= event.end_date
    
    def _is_upcoming_event(self, event: AcademicEvent, now: datetime) -> bool:
        """Check if event is upcoming"""
        return event.start_date > now
    
    def _event_to_dict(self, event: AcademicEvent) -> Dict:
        """Convert AcademicEvent to dictionary"""
        return {
            "id": event.event_id,
            "type": event.event_type.value,
            "title": event.title,
            "description": event.description,
            "start_date": event.start_date.isoformat(),
            "end_date": event.end_date.isoformat(),
            "course": event.course,
            "week": event.week,
            "priority": event.priority
        }

class AcademicCalendarManager:
    """
    Manages multiple academic calendars and integrates with Redis storage
    """
    
    def __init__(self, redis_client=None):
        """Initialize with optional Redis client for data persistence"""
        self.redis_client = redis_client
        self.calendars: Dict[str, AcademicCalendar] = {}
        self.default_institution = None
        
        # Load calendars from configuration
        self._load_calendar_configurations()
    
    def _load_calendar_configurations(self):
        """Load calendar configurations from config files - UPDATED with actual course codes"""
        # Updated configuration with real course codes
        
        default_config = {
            "name": "Abertay University",
            "term": {
                "start_date": "2025-05-19T00:00:00",
                "end_date": "2025-08-22T23:59:59",
                "total_weeks": 14,
                "teaching_weeks": 10,
                "holidays": []
            },
            "courses": {
                # CMP courses - Programming/Computer Science
                "CMP105": {  # Games Programming
                    "assignments": [
                        {
                            "id": "assignment1",
                            "title": "Basic Game Programming Assignment",
                            "description": "Implement fundamental game programming concepts",
                            "due_date": "2025-06-16T23:59:59"
                        }
                    ],
                    "projects": [
                        {
                            "id": "final_project",
                            "title": "Complete Game Development Project",
                            "description": "Develop a complete game using programming skills",
                            "due_date": "2025-08-18T23:59:59"
                        }
                    ]
                },
                "CMP201": {  # Data Structures and Algorithms 1
                    "assignments": [
                        {
                            "id": "data_structures_hw1",
                            "title": "Basic Data Structures Implementation",
                            "description": "Implement fundamental data structures",
                            "due_date": "2025-06-09T23:59:59"
                        }
                    ],
                    "exams": [
                        {
                            "id": "midterm",
                            "title": "Data Structures Midterm",
                            "description": "Covers basic data structures and algorithms",
                            "date": "2025-07-07T14:00:00"
                        }
                    ]
                },
                "CMP511": {  # Machine Learning and Artificial Intelligence
                    "assignments": [
                        {
                            "id": "ml_assignment1",
                            "title": "Linear Regression Implementation",
                            "description": "Implement linear regression from scratch",
                            "due_date": "2025-06-16T23:59:59"
                        },
                        {
                            "id": "ml_assignment2", 
                            "title": "Neural Network Project",
                            "description": "Build and train a neural network",
                            "due_date": "2025-07-14T23:59:59"
                        }
                    ],
                    "exams": [
                        {
                            "id": "midterm",
                            "title": "ML/AI Midterm Examination",
                            "description": "Covers weeks 1-7 material",
                            "date": "2025-07-07T14:00:00"
                        }
                    ],
                    "projects": [
                        {
                            "id": "final_project",
                            "title": "AI Application Project",
                            "description": "Develop a complete AI application",
                            "due_date": "2025-08-18T23:59:59"
                        }
                    ]
                },
                "MAT201": {  # Applied Mathematics 2
                    "assignments": [
                        {
                            "id": "calculus_hw1",
                            "title": "Advanced Calculus Problem Set",
                            "description": "Advanced derivatives and integration exercises",
                            "due_date": "2025-06-09T23:59:59"
                        }
                    ],
                    "exams": [
                        {
                            "id": "final_exam",
                            "title": "Applied Mathematics Final Exam",
                            "description": "Comprehensive final examination",
                            "date": "2025-08-15T09:00:00"
                        }
                    ]
                },
                "CMP203": {  # Graphics Programming
                    "assignments": [
                        {
                            "id": "graphics_basics",
                            "title": "Basic Graphics Programming",
                            "description": "Fundamental graphics programming exercises", 
                            "due_date": "2025-06-02T23:59:59"
                        }
                    ]
                },
                "DES502": {  # Game Design and Development
                    "assignments": [
                        {
                            "id": "game_concept",
                            "title": "Game Concept Document",
                            "description": "Design document for your game idea",
                            "due_date": "2025-06-23T23:59:59"
                        }
                    ]
                },
                "PSY555": {  # Human Psychology: In What Ways Are We All the Same?
                    "assignments": [
                        {
                            "id": "research_paper",
                            "title": "Human Psychology Research Paper",
                            "description": "Analysis of psychological commonalities among humans",
                            "due_date": "2025-07-07T23:59:59"
                        }
                    ]
                },
                "CMP304": {  # Artificial Intelligence
                    "assignments": [
                        {
                            "id": "ai_assignment1",
                            "title": "AI Search Algorithms",
                            "description": "Implement various AI search algorithms",
                            "due_date": "2025-06-30T23:59:59"
                        }
                    ]
                },
                "MAT501": {  # Applied Mathematics and AI
                    "assignments": [
                        {
                            "id": "math_ai_assignment",
                            "title": "Mathematical Foundations of AI",
                            "description": "Mathematical concepts underlying AI algorithms",
                            "due_date": "2025-07-21T23:59:59"
                        }
                    ]
                }
            }
        }
        
        # Create calendar for default institution
        self.calendars["abertay"] = AcademicCalendar(default_config)
        self.default_institution = "abertay"
        
        print(f"DEBUG: Loaded calendar for {default_config['name']}")
    
    def get_calendar(self, institution: str = None) -> AcademicCalendar:
        """Get calendar for specific institution or default"""
        if institution and institution in self.calendars:
            return self.calendars[institution]
        elif self.default_institution:
            return self.calendars[self.default_institution]
        else:
            raise ValueError("No academic calendar available")
    
    def get_academic_context(self, course: str = None, username: str = None, 
                           institution: str = None) -> Dict[str, Any]:
        """
        Get comprehensive academic context for AI tutor
        This is the main function your orchestrator will call
        """
        calendar = self.get_calendar(institution)
        
        if course:
            return calendar.get_course_specific_info(course, username)
        else:
            return calendar.get_current_academic_info()

def create_default_academic_calendar() -> AcademicCalendar:
    """
    Factory function to create a default academic calendar.
    This solves the initialization issue by providing proper configuration.
    """
    default_config = {
        "name": "Abertay University", 
        "term": {
            "start_date": "2025-05-19T00:00:00",
            "end_date": "2025-08-22T23:59:59",
            "total_weeks": 14,
            "teaching_weeks": 10,
            "holidays": []
        },
        "courses": {
            "CMP511": {  # Default course for testing
                "assignments": [
                    {
                        "id": "test_assignment",
                        "title": "Test Assignment",
                        "description": "Test assignment for debugging",
                        "due_date": "2025-07-01T23:59:59"
                    }
                ]
            }
        }
    }
    
    return AcademicCalendar(default_config)