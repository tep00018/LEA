"""
run_ragas_pipeline.py

Takes a generated question set (from generate_ragas_questions.py) and runs
each question through LEA's real RAG retrieval + answer generation pipeline,
producing (question, retrieved_contexts, answer) triples ready for RAGAS scoring.

This intentionally reuses RAGRetrievalTool directly -- the same retrieval path
Chat mode uses in streamlit_app.py -- so the evaluated pipeline matches
production behavior rather than a parallel/simplified retrieval implementation.

Usage:
    python run_ragas_pipeline.py \
        --questions ragas_questions_PSY555.json \
        --output ragas_triples_PSY555.json \
        --max-results 3
"""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from dotenv import load_dotenv

from src.mcp.tools.rag_retrieval_tool import RAGRetrievalTool

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Mirrors the production Chat-mode system prompt style (see get_enhanced_chat_fallback
# in streamlit_app.py) so the evaluated answer reflects real generation behavior.
ANSWER_GENERATION_PROMPT = """You are LEA, a helpful learning assistant for {course} at Abertay University.

COURSE CONTEXT:
Week {week} of {course}

RELEVANT COURSE CONTENT:
{context}

INSTRUCTIONS:
1. Answer the student's question using the course content when relevant
2. Be conversational and encouraging - you're LEA!
3. If the question isn't directly course-related, be helpful but try to connect to learning
4. Keep responses focused but comprehensive
5. Remember the motto: "Slide In. Study Up. Show Off."

Be natural, helpful, and educational."""


async def retrieve_context(rag_tool: RAGRetrievalTool, query: str, course: str, max_results: int) -> dict[str, Any]:
    """Call the real RAG retrieval tool, exactly as Chat mode does in production."""
    result = await rag_tool.execute({
        "query": query,
        "course": course,
        "max_results": max_results,
        "use_reranking": True,
    })
    return result


async def generate_answer(
    client: AsyncOpenAI,
    question: str,
    course: str,
    week: int,
    context_text: str,
) -> str:
    system_prompt = ANSWER_GENERATION_PROMPT.format(course=course, week=week, context=context_text[:2000])
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.7,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Answer generation failed for question '{question[:50]}...': {e}")
        return ""


async def process_question(
    rag_tool: RAGRetrievalTool,
    openai_client: AsyncOpenAI,
    record: dict[str, Any],
    max_results: int,
) -> dict[str, Any]:
    question = record["question"]
    course = record["course"]
    week = record.get("week_number", 1)

    rag_result = await retrieve_context(rag_tool, question, course, max_results)

    if not rag_result.get("success"):
        logger.warning(f"RAG retrieval failed for '{question[:50]}...': {rag_result.get('error')}")
        contexts = []
        context_text = ""
    else:
        contexts = [r["content"] for r in rag_result.get("results", [])]
        context_text = "\n\n".join(contexts)

    answer = await generate_answer(openai_client, question, course, week, context_text)

    return {
        **record,
        "contexts": contexts,
        "answer": answer,
        "retrieval_success": rag_result.get("success", False),
        "num_contexts_retrieved": len(contexts),
    }


async def main_async(args):
    with open(args.questions, "r", encoding="utf-8") as f:
        questions = json.load(f)

    logger.info(f"Loaded {len(questions)} questions from {args.questions}")

    rag_tool = RAGRetrievalTool()
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    results = []
    for i, record in enumerate(questions, 1):
        logger.info(f"[{i}/{len(questions)}] Processing: {record['question'][:60]}...")
        try:
            result = await process_question(rag_tool, openai_client, record, args.max_results)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed on question {i}: {e}")
            results.append({**record, "contexts": [], "answer": "", "retrieval_success": False, "error": str(e)})

        # Light rate-limit courtesy; adjust/remove if not needed
        await asyncio.sleep(0.2)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    success_count = sum(1 for r in results if r.get("retrieval_success"))
    logger.info(f"Done. {success_count}/{len(results)} retrievals succeeded. Output -> {args.output}")


def main():
    parser = argparse.ArgumentParser(description="Run question set through LEA's RAG + generation pipeline")
    parser.add_argument("--questions", required=True, help="Path to questions JSON from generate_ragas_questions.py")
    parser.add_argument("--output", required=True, help="Output path for RAGAS-ready triples")
    parser.add_argument("--max-results", type=int, default=3, help="Number of RAG chunks to retrieve per question")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()