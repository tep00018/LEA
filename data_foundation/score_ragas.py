"""
score_ragas.py

Scores a set of (question, contexts, answer) triples using the RAGAS
framework's four core metrics: faithfulness, answer relevance, context
precision, and context recall.

LIMITATION (documented for the paper): context_precision and context_recall
require a reference/ground-truth answer under RAGAS's standard design. No
human-authored reference answers exist for this evaluation, so this script
uses the generated answer itself as a stand-in ground truth. Faithfulness
and Answer Relevancy do not require a reference and are scored as RAGAS
intends; context_precision/context_recall should be read as measuring
internal consistency between retrieved context and the system's own
answer, not alignment with an independent ground truth.

Usage:
    python score_ragas.py --input ragas_triples_CMP511.json --output ragas_scores_CMP511.json
"""

import argparse
import json
import logging
import os

from datasets import Dataset
from dotenv import load_dotenv
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_triples(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_ragas_dataset(triples: list[dict], sample_size: int | None = None) -> Dataset:
    records = []
    for t in triples:
        if not t.get("retrieval_success") or not t.get("contexts") or not t.get("answer", "").strip():
            continue
        records.append({
            "question": t["question"],
            "contexts": t["contexts"],
            "answer": t["answer"],
            "ground_truth": t["answer"],
        })

    if sample_size and sample_size < len(records):
        records = records[:sample_size]

    logger.info(f"Built RAGAS dataset with {len(records)}/{len(triples)} usable records")
    return Dataset.from_list(records)


def main():
    parser = argparse.ArgumentParser(description="Score RAGAS triples")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--sample-size", type=int, default=None,
                         help="Optional cap on number of records scored (for cost/testing)")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in environment")

    triples = load_triples(args.input)
    dataset = build_ragas_dataset(triples, args.sample_size)

    judge_llm = ChatOpenAI(model=args.model, api_key=api_key)
    judge_embeddings = OpenAIEmbeddings(api_key=api_key)

    logger.info(f"Scoring {len(dataset)} records with RAGAS (judge model: {args.model})...")

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge_llm,
        embeddings=judge_embeddings,
    )

    # Avoid result.to_pandas() -- pyarrow/pandas/numpy version interop bug.
    # Access scores directly instead.
    scores_dict = result._scores_dict if hasattr(result, "_scores_dict") else dict(result)

    def safe_mean(values):
        clean = [v for v in values if v is not None]
        return float(sum(clean) / len(clean)) if clean else None

    # Avoid result.to_pandas() -- hits a pyarrow/pandas/numpy version interop bug.
    # Result is itself a dict of aggregate scores; per-record detail lives in
    # result.scores (a Dataset), aligned row-for-row with the input dataset.
    aggregate = {
        "faithfulness": float(result["faithfulness"]),
        "answer_relevancy": float(result["answer_relevancy"]),
        "context_precision": float(result["context_precision"]),
        "context_recall": float(result["context_recall"]),
        "n_records_scored": len(dataset),
        "n_records_total": len(triples),
        "n_records_excluded": len(triples) - len(dataset),
    }

    per_record_scores = []
    for i in range(len(result.scores)):
        row_scores = result.scores[i]
        per_record_scores.append({
            "faithfulness": row_scores.get("faithfulness"),
            "answer_relevancy": row_scores.get("answer_relevancy"),
            "context_precision": row_scores.get("context_precision"),
            "context_recall": row_scores.get("context_recall"),
            "question": dataset[i]["question"],
            "answer": dataset[i]["answer"],
        })

    output = {
        "aggregate_scores": aggregate,
        "per_record_scores": per_record_scores,
    }

    # aggregate = {
    #     "faithfulness": safe_mean(scores_dict.get("faithfulness", [])),
    #     "answer_relevancy": safe_mean(scores_dict.get("answer_relevancy", [])),
    #     "context_precision": safe_mean(scores_dict.get("context_precision", [])),
    #     "context_recall": safe_mean(scores_dict.get("context_recall", [])),
    #     "n_records_scored": len(dataset),
    #     "n_records_total": len(triples),
    #     "n_records_excluded": len(triples) - len(dataset),
    # }

    # n = len(dataset)
    # per_record_scores = []
    # for i in range(n):
    #     per_record_scores.append({
    #         "faithfulness": scores_dict.get("faithfulness", [None] * n)[i],
    #         "answer_relevancy": scores_dict.get("answer_relevancy", [None] * n)[i],
    #         "context_precision": scores_dict.get("context_precision", [None] * n)[i],
    #         "context_recall": scores_dict.get("context_recall", [None] * n)[i],
    #         "question": dataset[i]["question"],
    #         "answer": dataset[i]["answer"],
    #     })

    # output = {
    #     "aggregate_scores": aggregate,
    #     "per_record_scores": per_record_scores,
    # }
    
    
    # result_df = result.to_pandas()

    # aggregate = {
    #     "faithfulness": float(result_df["faithfulness"].mean()),
    #     "answer_relevancy": float(result_df["answer_relevancy"].mean()),
    #     "context_precision": float(result_df["context_precision"].mean()),
    #     "context_recall": float(result_df["context_recall"].mean()),
    #     "n_records_scored": len(result_df),
    #     "n_records_total": len(triples),
    #     "n_records_excluded": len(triples) - len(result_df),
    # }

    # output = {
    #     "aggregate_scores": aggregate,
    #     "per_record_scores": result_df.to_dict(orient="records"),
    # }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print("\n" + "=" * 50)
    print(f"RAGAS RESULTS: {args.input}")
    print("=" * 50)
    for k, v in aggregate.items():
        print(f"  {k}: {v}")
    print(f"\nFull results written to {args.output}")


if __name__ == "__main__":
    main()