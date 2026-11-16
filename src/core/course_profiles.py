"""Course profiles: which programming language (if any) a course teaches.

A profile is a small JSON file, ``data/course_profiles/<COURSE>.json``::

    {"code": "DEMO101", "name": "Introduction to AI/ML",
     "programming_language": "python", "allow_code_questions": true}

* ``programming_language``: a short key such as ``"python"`` or ``"cpp"``, or ``null`` for a
  course with no programming (a humanities, mathematics or design course, for example). Quizzes never contain code
  for such a course.
* ``allow_code_questions``: lets an instructor switch code questions off for a course that
  does have a language.

A course with no profile file is treated as having no programming language, so it never gets
code questions by accident.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from src.core.config import COURSE_PROFILES_DIR

logger = logging.getLogger(__name__)

# Display name used in prompts. Any key not listed is shown as written, e.g. "kotlin" -> "Kotlin".
LANGUAGE_LABELS: Dict[str, str] = {
    "python": "Python", "cpp": "C++", "c": "C", "csharp": "C#", "java": "Java", "javascript": "JavaScript",
    "typescript": "TypeScript", "r": "R", "sql": "SQL", "matlab": "MATLAB", "go": "Go", "rust": "Rust",
}

# Short worked examples shown to the question generator, by language. Languages without an entry
# fall back to a generic instruction that does not contain any other language's code.
CODE_EXAMPLES: Dict[str, Dict[str, str]] = {
    "python": {
        "output": "What will this code output?\n```python\nfor i in range(3):\n    print(i)\n```",
        "error": "Find the error in this code:\n```python\ndef add(a, b):\n    return a + b\nresult = add(5)\n```",
        "snippet": "x = [1, 2, 3]\nprint(x[0])",
    },
    "cpp": {
        "output": 'What will this code output?\n```cpp\nfor (int i = 0; i < 3; ++i) {\n    std::cout << i << " ";\n}\n```',
        "error": "Find the error in this code:\n```cpp\nint add(int a, int b) {\n    return a + b;\n}\nint result = add(5);\n```",
        "snippet": "std::vector<int> x = {1, 2, 3};\nstd::cout << x[0];",
    },
}


@dataclass(frozen=True)
class CourseProfile:
    code: str
    name: str = ""
    programming_language: Optional[str] = None
    allow_code_questions: bool = True

    @property
    def has_code(self) -> bool:
        """True when quizzes for this course may contain code."""
        return bool(self.programming_language) and self.allow_code_questions

    @property
    def language_key(self) -> Optional[str]:
        return self.programming_language.strip().lower() if self.programming_language else None

    @property
    def language_label(self) -> str:
        """Name of the language for prompts ("Python", "C++"); "code" for a course without one."""
        key = self.language_key
        if not key:
            return "code"
        return LANGUAGE_LABELS.get(key, key[:1].upper() + key[1:])

    @property
    def code_fence(self) -> str:
        """Markdown code-fence tag for the language ("python", "cpp"); empty if there is none."""
        return self.language_key or ""

    def code_example(self, kind: str) -> str:
        """A short example question of ``kind`` ("output", "error", "snippet") in this language."""
        examples = CODE_EXAMPLES.get(self.language_key or "")
        if examples:
            return examples[kind]
        fence = self.code_fence
        generic = {
            "output": f"What will this code output?\n```{fence}\n<3-10 lines of {self.language_label}>\n```",
            "error": f"Find the error in this code:\n```{fence}\n<3-10 lines of {self.language_label}>\n```",
            "snippet": f"<a short {self.language_label} snippet>",
        }
        return generic[kind]

    def code_example_json(self, kind: str) -> str:
        """The same example with line breaks and quotes escaped, for use inside a JSON sample."""
        return json.dumps(self.code_example(kind))[1:-1]


def load_course_profile(course: str, profiles_dir: Optional[Path] = None) -> CourseProfile:
    """Read ``<profiles_dir>/<course>.json``; a missing or unreadable file gives a profile with no language."""
    base = Path(profiles_dir) if profiles_dir is not None else COURSE_PROFILES_DIR
    path = base / f"{course}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.info("No course profile for %s (%s); treating it as a course without code", course, path)
        return CourseProfile(code=course, name=course)
    except (OSError, ValueError) as exc:
        logger.warning("Could not read course profile %s: %s; treating %s as a course without code", path, exc, course)
        return CourseProfile(code=course, name=course)
    language = raw.get("programming_language")
    return CourseProfile(
        code=str(raw.get("code") or course),
        name=str(raw.get("name") or course),
        programming_language=str(language).strip() or None if language is not None else None,
        allow_code_questions=bool(raw.get("allow_code_questions", True)),
    )


def get_course_profile(course: Optional[str] = None, profiles_dir: Optional[Path] = None) -> CourseProfile:
    """Profile for ``course`` (the default course if omitted)."""
    if not course:
        from src.core.config import DEFAULT_COURSE

        course = DEFAULT_COURSE
    return load_course_profile(course, profiles_dir)
