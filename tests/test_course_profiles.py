"""Course profiles and course discovery."""

import json

import pytest

from src.core import config, course_profiles
from src.core.config import DEFAULT_COURSE, discover_courses
from src.core.course_profiles import CourseProfile, load_course_profile


def write_profile(folder, code, **fields):
    (folder / f"{code}.json").write_text(json.dumps({"code": code, "name": f"{code} course", **fields}), encoding="utf-8")


def test_default_course_is_the_demo_course():
    assert DEFAULT_COURSE == "DEMO101"


def test_demo_profile_ships_with_python():
    profile = load_course_profile("DEMO101")
    assert profile.programming_language == "python"
    assert profile.allow_code_questions is True
    assert profile.has_code
    assert profile.language_label == "Python"


def test_missing_profile_means_no_code(tmp_path):
    profile = load_course_profile("NOPROFILE", tmp_path)
    assert profile.programming_language is None
    assert not profile.has_code


def test_null_language_means_no_code(tmp_path):
    write_profile(tmp_path, "HUM200", programming_language=None)
    profile = load_course_profile("HUM200", tmp_path)
    assert profile.programming_language is None
    assert not profile.has_code
    assert profile.language_label == "code"


def test_code_can_be_switched_off_for_a_course_with_a_language(tmp_path):
    write_profile(tmp_path, "PY200", programming_language="python", allow_code_questions=False)
    assert not load_course_profile("PY200", tmp_path).has_code


@pytest.mark.parametrize("key,label", [("python", "Python"), ("cpp", "C++"), ("csharp", "C#"), ("kotlin", "Kotlin")])
def test_language_labels(key, label):
    assert CourseProfile(code="X", programming_language=key).language_label == label


def test_unreadable_profile_is_treated_as_no_code(tmp_path):
    (tmp_path / "BAD100.json").write_text("{not json", encoding="utf-8")
    assert not load_course_profile("BAD100", tmp_path).has_code


def test_discover_courses_lists_kc_model_folders(tmp_path):
    (tmp_path / "B200").mkdir()
    (tmp_path / "A100").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert discover_courses(tmp_path) == ["A100", "B200"]


def test_discover_courses_falls_back_to_the_default(tmp_path):
    assert discover_courses(tmp_path / "does-not-exist") == [DEFAULT_COURSE]


def test_repository_only_contains_the_demo_course():
    assert discover_courses(config.KC_MODELS_DIR) == ["DEMO101"]


def test_profiles_dir_is_patchable(tmp_path, monkeypatch):
    write_profile(tmp_path, "CPP300", programming_language="cpp")
    monkeypatch.setattr(course_profiles, "COURSE_PROFILES_DIR", tmp_path)
    assert course_profiles.get_course_profile("CPP300").language_label == "C++"
