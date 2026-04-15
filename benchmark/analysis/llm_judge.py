import argparse
import csv
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

from openai import OpenAI
from pypdf import PdfReader


DEFAULT_BASE_URL = "http://40.82.143.121:9008/v1"
DEFAULT_OUTPUT_CSV = "benchmark/analysis/llm_judge_results.csv"
DEFAULT_OUTPUT_JSON = "benchmark/analysis/llm_judge_results.json"


def normalize_for_matching(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def ensure_v1_base_url(base_url: str) -> str:
    return base_url.rstrip("/") if base_url.rstrip("/").endswith("/v1") else f"{base_url.rstrip('/')}/v1"


def match_markdown_files(file_id: str, benchmark_dir: Path) -> Dict[str, Path]:
    matches: Dict[str, Path] = {}
    normalized_file_id = normalize_for_matching(file_id)
    for md_file in benchmark_dir.glob("*.md"):
        normalized_stem = normalize_for_matching(md_file.stem)
        if normalized_file_id in normalized_stem:
            if "_2md_" in normalized_stem:
                matches["2md"] = md_file
            elif "_markitdown_" in normalized_stem:
                matches["markitdown"] = md_file
    return matches


def read_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(pdf_path)
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(page for page in pages if page).strip()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def excerpt_text(text: str, max_chars: int = 4500, sections: int = 3) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text

    sections = max(1, sections)
    chunk_size = max(300, max_chars // sections)
    anchors = [0]
    if sections >= 2:
        anchors.append(max(0, (len(text) // 2) - (chunk_size // 2)))
    if sections >= 3:
        anchors.append(max(0, len(text) - chunk_size))

    unique_anchors: List[int] = []
    for anchor in anchors:
        if anchor not in unique_anchors:
            unique_anchors.append(anchor)

    parts = []
    for idx, anchor in enumerate(unique_anchors, start=1):
        snippet = text[anchor:anchor + chunk_size].strip()
        parts.append(f"[Excerpt {idx}]\n{snippet}")

    return "\n\n...\n\n".join(parts)


def load_numeric_context(csv_path: Path) -> Dict[str, Dict[str, str]]:
    if not csv_path.exists():
        return {}

    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    return {row["File"]: row for row in rows}


def build_user_prompt(
    file_id: str,
    pdf_excerpt: str,
    md_2md_excerpt: str,
    md_markitdown_excerpt: str,
    numeric_row: Optional[Dict[str, str]],
) -> str:
    counts_block = ""
    if numeric_row:
        counts_block = f"""
Objective structure counts from the benchmark:
- PDF counts: headers={numeric_row.get('PDF_Headers')}, lists={numeric_row.get('PDF_Lists')}, tables={numeric_row.get('PDF_Tables')}, images={numeric_row.get('PDF_Images')}
- 2md counts: headers={numeric_row.get('2md_MdHeaders')}, lists={numeric_row.get('2md_MdLists')}, tables={numeric_row.get('2md_MdTables')}, images={numeric_row.get('2md_MdImages')}
- markitdown counts: headers={numeric_row.get('markitdown_MdHeaders')}, lists={numeric_row.get('markitdown_MdLists')}, tables={numeric_row.get('markitdown_MdTables')}, images={numeric_row.get('markitdown_MdImages')}
""".strip()

    return f"""
Evaluate two Markdown conversions of the same PDF.

File: {file_id}

Rubric:
- faithfulness_to_pdf: factual/content fidelity to the PDF text
- structure_preservation: preservation of headings, list hierarchy, table-like organization, and layout meaning
- table_preservation: quality of preserving tabular content and relationships
- readability: how usable and readable the Markdown is
- hallucination_control: whether the Markdown avoids adding content/noise not supported by the PDF
- overall: overall judgment for this document

Score each dimension from 1 to 5 where 5 is best.
Use the PDF as the ground truth.
Prefer concrete evidence from the excerpts.
Be strict about hallucinated or unsupported content.
If a dimension is not really applicable, still score it based on what is visible in the excerpts.

Return strict JSON only, with this exact shape:
{{
  "file": "<file id>",
  "scores": {{
    "2md": {{
      "faithfulness_to_pdf": 0,
      "structure_preservation": 0,
      "table_preservation": 0,
      "readability": 0,
      "hallucination_control": 0,
      "overall": 0
    }},
    "markitdown": {{
      "faithfulness_to_pdf": 0,
      "structure_preservation": 0,
      "table_preservation": 0,
      "readability": 0,
      "hallucination_control": 0,
      "overall": 0
    }}
  }},
  "winner": "2md | markitdown | tie",
  "reasoning": "short paragraph",
  "evidence": ["evidence item 1", "evidence item 2", "evidence item 3"]
}}

{counts_block}

PDF excerpt:
```text
{pdf_excerpt}
```

2md Markdown excerpt:
```md
{md_2md_excerpt}
```

markitdown Markdown excerpt:
```md
{md_markitdown_excerpt}
```
""".strip()


def extract_json_object(text: str) -> Dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")

    candidate = match.group(0)
    candidate = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", candidate)
    return json.loads(candidate)


def flatten_result(file_id: str, result: Dict) -> Dict[str, object]:
    row: Dict[str, object] = {"File": file_id, "Winner": result.get("winner", ""), "Reasoning": result.get("reasoning", "")}
    evidence = result.get("evidence", [])
    row["Evidence"] = " | ".join(evidence) if isinstance(evidence, list) else str(evidence)

    for tool in ["2md", "markitdown"]:
        tool_scores = result.get("scores", {}).get(tool, {})
        row[f"{tool}_Faithfulness"] = tool_scores.get("faithfulness_to_pdf", "")
        row[f"{tool}_Structure"] = tool_scores.get("structure_preservation", "")
        row[f"{tool}_TablePreservation"] = tool_scores.get("table_preservation", "")
        row[f"{tool}_Readability"] = tool_scores.get("readability", "")
        row[f"{tool}_HallucinationControl"] = tool_scores.get("hallucination_control", "")
        row[f"{tool}_Overall"] = tool_scores.get("overall", "")

    return row


def judge_file(
    client: OpenAI,
    model: str,
    file_id: str,
    pdf_path: Path,
    md_files: Dict[str, Path],
    numeric_row: Optional[Dict[str, str]],
    max_chars: int,
) -> Dict:
    pdf_text = read_pdf_text(pdf_path)
    md_2md = read_text(md_files["2md"])
    md_markitdown = read_text(md_files["markitdown"])

    prompt = build_user_prompt(
        file_id=file_id,
        pdf_excerpt=excerpt_text(pdf_text, max_chars=max_chars),
        md_2md_excerpt=excerpt_text(md_2md, max_chars=max_chars),
        md_markitdown_excerpt=excerpt_text(md_markitdown, max_chars=max_chars),
        numeric_row=numeric_row,
    )

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict document-conversion judge. "
                    "Evaluate faithfulness to the PDF ground truth, structure preservation, "
                    "table preservation, readability, and hallucination control. "
                    "Return strict JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    content = response.choices[0].message.content or ""
    parsed = extract_json_object(content)
    parsed["_raw_response"] = content
    return parsed


def write_csv(rows: List[Dict[str, object]], output_path: Path) -> None:
    if not rows:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Supplementary LLM-as-a-judge benchmark for PDF-to-Markdown outputs.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--benchmark-dir", default="benchmark")
    parser.add_argument("--base-url", default=os.getenv("LLM_JUDGE_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.getenv("LLM_JUDGE_API_KEY", os.getenv("OPENAI_API_KEY")))
    parser.add_argument("--model", default=os.getenv("LLM_JUDGE_MODEL"))
    parser.add_argument("--numeric-csv", default="benchmark/analysis/comprehensive_evaluation.csv")
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-json", default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--max-chars", type=int, default=4500)
    parser.add_argument("--file", dest="file_filter", default=None, help="Optional exact PDF stem to judge.")
    parser.add_argument("--list-models", action="store_true")
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Missing API key. Set --api-key or LLM_JUDGE_API_KEY / OPENAI_API_KEY.")

    client = OpenAI(base_url=ensure_v1_base_url(args.base_url), api_key=args.api_key)

    if args.list_models:
        models = client.models.list()
        for model in models.data:
            print(model.id)
        return

    if not args.model:
        raise SystemExit("Missing model name. Set --model or LLM_JUDGE_MODEL.")

    data_dir = Path(args.data_dir)
    benchmark_dir = Path(args.benchmark_dir)
    numeric_context = load_numeric_context(Path(args.numeric_csv))

    all_rows: List[Dict[str, object]] = []
    raw_results: List[Dict] = []

    for pdf_path in sorted(data_dir.glob("*.pdf")):
        file_id = pdf_path.stem
        if args.file_filter and file_id != args.file_filter:
            continue

        md_files = match_markdown_files(file_id, benchmark_dir)
        if "2md" not in md_files or "markitdown" not in md_files:
            print(f"Skipping {file_id}: missing matched Markdown outputs.")
            continue

        print(f"Judging {file_id}...")
        result = judge_file(
            client=client,
            model=args.model,
            file_id=file_id,
            pdf_path=pdf_path,
            md_files=md_files,
            numeric_row=numeric_context.get(file_id),
            max_chars=args.max_chars,
        )
        raw_results.append(result)
        all_rows.append(flatten_result(file_id, result))

    write_csv(all_rows, Path(args.output_csv))
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(json.dumps(raw_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved CSV to {args.output_csv}")
    print(f"Saved JSON to {args.output_json}")


if __name__ == "__main__":
    main()
