"""Quiz generation follows the course profile (paper Section 5.4)."""

import json

import pytest

from src.core import course_profiles
from src.quiz.simple_quiz_system import SimpleQuizSystem


def write_profile(folder, code, **fields):
    (folder / f"{code}.json").write_text(json.dumps({"code": code, "name": f"{code} course", **fields}), encoding="utf-8")


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(course_profiles, "COURSE_PROFILES_DIR", tmp_path)
    return tmp_path


def make_quiz():
    """A quiz system without an OpenAI client or Redis: these tests only build prompts and decisions."""
    quiz = SimpleQuizSystem.__new__(SimpleQuizSystem)
    quiz.question_history = {}
    return quiz


def plan(number, **extra):
    """A plan that would normally be a high-priority coding question."""
    base = {"quiz_id": "q1", "question_number": number, "total_questions": 11, "type": "multiple_choice",
            "skill_name": "Implement an algorithm", "skill_category": "application", "cognitive_level": "apply",
            "complexity": "advanced", "description": "Implement and debug a small program",
            "go_id": "GO_1", "lo_id": "LO_1", "keywords": []}
    base.update(extra)
    return base


def test_profile_with_no_language_never_generates_code_questions(profiles):
    write_profile(profiles, "HUM200", programming_language=None)
    quiz = make_quiz()
    for number in range(1, 12):
        assert quiz._should_include_coding_question_from_plan(plan(number), "HUM200") is False


def test_course_is_read_from_the_plan_when_not_passed(profiles):
    write_profile(profiles, "HUM200", programming_language=None)
    quiz = make_quiz()
    assert quiz._should_include_coding_question_from_plan(plan(4, course="HUM200")) is False


def test_course_without_a_profile_never_generates_code_questions(profiles):
    quiz = make_quiz()
    for number in range(1, 12):
        assert quiz._should_include_coding_question_from_plan(plan(number), "NO-PROFILE") is False


def test_switching_code_off_in_the_profile_stops_code_questions(profiles):
    write_profile(profiles, "PY200", programming_language="python", allow_code_questions=False)
    quiz = make_quiz()
    assert quiz._should_include_coding_question_from_plan(plan(4), "PY200") is False


def test_course_with_a_language_still_gets_code_questions(profiles):
    write_profile(profiles, "PY200", programming_language="python")
    quiz = make_quiz()
    decisions = [quiz._should_include_coding_question_from_plan(plan(n, quiz_id=f"q{n}"), "PY200") for n in range(1, 12)]
    assert any(decisions)


def test_prompt_for_a_course_with_no_language_asks_for_no_code(profiles):
    write_profile(profiles, "HUM200", programming_language=None)
    prompt = make_quiz()._create_enhanced_generation_prompt(plan(5, course="HUM200", include_code=True), "some content")
    assert "DO NOT include code" in prompt
    assert "CODING QUESTION" not in prompt


def test_cpp_profile_prompts_for_cpp_not_python(profiles):
    write_profile(profiles, "CPP300", programming_language="cpp")
    prompt = make_quiz()._create_enhanced_generation_prompt(plan(5, course="CPP300", include_code=True), "some content")
    assert "actual C++ code" in prompt
    assert "```cpp" in prompt
    assert "std::" in prompt
    assert "Python" not in prompt
    assert "```python" not in prompt
    assert "Q-learning" not in prompt


def test_python_profile_prompts_for_python(profiles):
    write_profile(profiles, "PY200", programming_language="python")
    prompt = make_quiz()._create_enhanced_generation_prompt(plan(5, course="PY200", include_code=True), "some content")
    assert "actual Python code" in prompt
    assert "```python" in prompt
    assert "C++" not in prompt


def test_unlisted_language_gets_a_generic_prompt_without_other_languages_code(profiles):
    write_profile(profiles, "KT100", programming_language="kotlin")
    prompt = make_quiz()._create_enhanced_generation_prompt(plan(5, course="KT100", include_code=True), "some content")
    assert "actual Kotlin code" in prompt
    assert "```kotlin" in prompt
    assert "Python" not in prompt and "std::" not in prompt


def test_code_fences_are_only_auto_added_for_python():
    quiz = make_quiz()
    unfenced = "from sklearn.linear_model import LinearRegression\nfrom sklearn.tree import DecisionTreeClassifier"
    assert quiz._format_code_blocks(unfenced, "cpp") == unfenced
    assert quiz._format_code_blocks(unfenced, None) == unfenced
    assert "```python" in quiz._format_code_blocks(unfenced, "python")
    assert quiz._format_code_blocks("```cpp\nint x;\n```", "cpp") == "```cpp\nint x;\n```"
