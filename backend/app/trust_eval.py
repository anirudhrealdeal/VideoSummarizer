"""
trust_eval.py — LLM-as-judge evaluation suite for video summaries.

Three evaluators, three GPT-4o-mini calls:
  1. Faithfulness  — each key point grounded in the transcript (score + attribution)
  2. Hallucination + Safety — narration sentences not supported by source + framing issues
  3. Engagement    — is the narration script genuinely written for speech?
"""

import json
import re
from typing import List, Dict
from openai import OpenAI
import os


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is required")
    return OpenAI(api_key=api_key)


def _safe_json(text: str, fallback):
    """Extract first JSON object/array from LLM output, return fallback on failure."""
    match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    return fallback


# ---------------------------------------------------------------------------
# Evaluator 1: Faithfulness
# ---------------------------------------------------------------------------

def eval_faithfulness(key_points: List[str], transcript: str) -> Dict:
    """
    For each key point, ask the judge whether it is supported by the transcript.
    Returns a score (0.0–1.0) per point and the best supporting quote.
    """
    client = _get_client()
    points_json = json.dumps(key_points, indent=2)

    prompt = (
        "You are a strict factual auditor. Given a list of key points and a transcript, "
        "evaluate whether each key point is genuinely supported by the transcript.\n\n"
        "For each key point output a JSON object in this array:\n"
        "[\n"
        "  {\n"
        '    "point": "<the key point verbatim>",\n'
        '    "score": <0.0 to 1.0 — 1.0 means clearly supported, 0.0 means not found at all>,\n'
        '    "verdict": "supported" | "partially supported" | "not found",\n'
        '    "quote": "<shortest transcript excerpt that supports it, or empty string if not found>"\n'
        "  }\n"
        "]\n\n"
        "Return ONLY the JSON array, no other text.\n\n"
        f"Key points:\n{points_json}\n\n"
        f"Transcript (may be truncated):\n{transcript[:6000]}"
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
    )
    raw = resp.choices[0].message.content.strip()
    results = _safe_json(raw, [])

    scores = [r.get("score", 0.0) for r in results if isinstance(r, dict)]
    overall = round(sum(scores) / len(scores), 2) if scores else 0.0

    return {
        "overall_score": overall,
        "per_point": results,
    }


# ---------------------------------------------------------------------------
# Evaluator 2: Hallucination + Safety
# ---------------------------------------------------------------------------

def eval_hallucination_and_safety(narration_script: str, transcript: str) -> Dict:
    """
    Check whether the narration introduces claims not in the transcript,
    and whether any framing is misleading or sensationalist.
    """
    client = _get_client()

    prompt = (
        "You are a rigorous fact-checker and media ethics reviewer. "
        "You will be given a narration script derived from a transcript. "
        "Your job is to find two types of problems:\n\n"
        "1. HALLUCINATIONS — specific sentences in the narration that assert facts, "
        "numbers, names, or claims NOT present in the transcript.\n"
        "2. FRAMING ISSUES — sentences that exaggerate, sensationalise, or misrepresent "
        "the source material even if technically derived from it.\n\n"
        "Return a single JSON object:\n"
        "{\n"
        '  "hallucinations": [\n'
        '    {"sentence": "<narration sentence>", "issue": "<what is wrong>"}\n'
        "  ],\n"
        '  "framing_issues": [\n'
        '    {"sentence": "<narration sentence>", "issue": "<what is misleading>"}\n'
        "  ],\n"
        '  "hallucination_risk": "low" | "medium" | "high",\n'
        '  "safety_verdict": "clean" | "minor concerns" | "review needed"\n'
        "}\n\n"
        "If none found, return empty arrays. Return ONLY JSON.\n\n"
        f"Transcript (source):\n{transcript[:4000]}\n\n"
        f"Narration script:\n{narration_script[:3000]}"
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
    )
    raw = resp.choices[0].message.content.strip()
    result = _safe_json(raw, {
        "hallucinations": [],
        "framing_issues": [],
        "hallucination_risk": "unknown",
        "safety_verdict": "unknown",
    })
    return result


# ---------------------------------------------------------------------------
# Evaluator 3: Engagement quality
# ---------------------------------------------------------------------------

def eval_engagement(narration_script: str) -> Dict:
    """
    Score the narration script on how well it is written for speech vs document prose.
    """
    client = _get_client()

    prompt = (
        "You are an expert in science communication and spoken-word storytelling. "
        "Evaluate this narration script on three dimensions, each scored 1–10:\n\n"
        "- hook_strength: Does the opening grab attention immediately? Is it original?\n"
        "- rhythm: Does sentence length vary? Does it flow naturally when read aloud?\n"
        "- clarity: Are ideas explained accessibly without being dumbed down?\n\n"
        "Also write one sentence of actionable feedback for improvement.\n\n"
        "Return ONLY this JSON:\n"
        "{\n"
        '  "hook_strength": <1-10>,\n'
        '  "rhythm": <1-10>,\n'
        '  "clarity": <1-10>,\n'
        '  "overall": <average of the three, rounded to 1 decimal>,\n'
        '  "feedback": "<one sentence>"\n'
        "}\n\n"
        f"Narration script:\n{narration_script[:3000]}"
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
    )
    raw = resp.choices[0].message.content.strip()
    result = _safe_json(raw, {
        "hook_strength": 0,
        "rhythm": 0,
        "clarity": 0,
        "overall": 0,
        "feedback": "Could not evaluate.",
    })
    return result


# ---------------------------------------------------------------------------
# Combined runner
# ---------------------------------------------------------------------------

def run_trust_eval(
    key_points: List[str],
    narration_script: str,
    transcript: str,
) -> Dict:
    """Run all three evaluators and return a combined trust report."""
    print("Running trust evaluation — faithfulness...")
    faithfulness = eval_faithfulness(key_points, transcript)

    print("Running trust evaluation — hallucination + safety...")
    hal_safety = eval_hallucination_and_safety(narration_script, transcript)

    print("Running trust evaluation — engagement...")
    engagement = eval_engagement(narration_script)

    # Compute an overall trust score (0–100)
    faith_score = faithfulness.get("overall_score", 0) * 40        # 40 pts
    hal_risk_map = {"low": 30, "medium": 15, "high": 0, "unknown": 20}
    hal_score = hal_risk_map.get(hal_safety.get("hallucination_risk", "unknown"), 20)  # 30 pts
    eng_score = (engagement.get("overall", 0) / 10) * 30           # 30 pts
    trust_score = round(faith_score + hal_score + eng_score)

    return {
        "trust_score": trust_score,          # 0–100
        "faithfulness": faithfulness,
        "hallucination_safety": hal_safety,
        "engagement": engagement,
    }
