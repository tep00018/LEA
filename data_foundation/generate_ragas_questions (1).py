"""
generate_ragas_questions.py

Generates a RAGAS-ready question set for one course, derived directly from
that course's KC model -- mirroring the original Chat simulation's approach
of generating questions "germane" to each week's GOs, but without the
learner-persona simulation layer (RAGAS only needs question/context/answer
triples, not synthetic learner variation).

Usage:
    python generate_ragas_questions.py --course PSY555 \
        --kc-model data/kc_models/PSY555/kc_model_PSY555.json \
        --questions-per-go 2 \
        --output ragas_questions_PSY555.json
"""

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

QUESTION_GENERATION_PROMPT = """You are generating realistic student questions for a course evaluation.

Course: {course}
Week: {week_number} ({week_name})
Learning Objective: {lo_title}
Granular Objective (skill to be assessed): {skill_name}
GO description: {description}

Generate {n} distinct, realistic questions that a student in this course might ask
about this specific topic. Questions should:
- Be the kind of thing a real student would type into a chat-based course assistant
- Vary in style (one conceptual/clarifying, one applied/example-seeking, etc. if n>1)
- NOT directly quote the GO description verbatim
- Be answerable using course materials on this topic

Return ONLY a JSON array of strings, e.g. ["question 1", "question 2"]. No other text.
"""


def load_kc_model(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_questions_for_go(
    client: OpenAI,
    course: str,
    week_number: int,
    week_name: str,
    lo_title: str,
    skill_name: str,
    description: str,
    n: int,
) -> list[str]:
    prompt = QUESTION_GENERATION_PROMPT.format(
        course=course,
        week_number=week_number,
        week_name=week_name,
        lo_title=lo_title,
        skill_name=skill_name,
        description=description,
        n=n,
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        questions = json.loads(raw)
        if not isinstance(questions, list):
            raise ValueError("Expected a JSON array")
        return [str(q) for q in questions][:n]
    except Exception as e:
        logger.warning(f"Question generation failed for GO '{skill_name}': {e}")
        # Fallback: a generic templated question so the pipeline doesn't silently drop GOs
        return [f"Can you explain {skill_name.lower()}?"][:n]


def main():
    parser = argparse.ArgumentParser(description="Generate RAGAS question set from a KC model")
    parser.add_argument("--course", required=True, help="Course code, e.g. PSY555")
    parser.add_argument("--kc-model", required=True, help="Path to kc_model_<COURSE>.json")
    parser.add_argument("--questions-per-go", type=int, default=2)
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="Optional hard cap on total questions generated (stops early once reached)",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in environment")
    client = OpenAI(api_key=api_key)

    kc_model = load_kc_model(args.kc_model)
    week_nav = kc_model.get("week_navigation", {})

    records = []
    for week_key in sorted(week_nav.keys()):
        week_data = week_nav[week_key]
        week_number = week_data.get("week_number")
        week_name = week_data.get("week_name", week_data.get("week_display", f"Week {week_number}"))

        for lo in week_data.get("learning_objectives", []):
            lo_id = lo.get("lo_id")
            lo_title = lo.get("title", lo.get("short_title", ""))

            for go in lo.get("granular_objectives", []):
                if args.max_questions and len(records) >= args.max_questions:
                    break

                go_id = go.get("go_id")
                skill_name = go.get("skill_name", "")
                description = go.get("description", "")

                logger.info(f"Generating questions for {go_id}: {skill_name}")
                questions = generate_questions_for_go(
                    client=client,
                    course=args.course,
                    week_number=week_number,
                    week_name=week_name,
                    lo_title=lo_title,
                    skill_name=skill_name,
                    description=description,
                    n=args.questions_per_go,
                )

                for q in questions:
                    records.append({
                        "course": args.course,
                        "week_number": week_number,
                        "week_name": week_name,
                        "lo_id": lo_id,
                        "go_id": go_id,
                        "skill_name": skill_name,
                        "question": q,
                    })

            if args.max_questions and len(records) >= args.max_questions:
                break
        if args.max_questions and len(records) >= args.max_questions:
            break

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    logger.info(f"Generated {len(records)} questions for {args.course} -> {args.output}")


if __name__ == "__main__":
    main()