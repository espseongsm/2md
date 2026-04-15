# 2md

A fast, memory-safe CLI tool written in Rust to convert PDF documents into well-formatted Markdown files.

## Features

- **PDF to Markdown Conversion**: Extracts text from PDFs and intelligently formats it into readable Markdown, removing unnecessary line breaks and establishing paragraphs.
- **Table Extraction**: Intelligent splitting logic parses PDF tabular data and translates it into well-formed Markdown tables.
- **Image Extraction**: Discovers embedded images directly within the PDF, extracts and saves them locally as `.png` files, and automatically injects image tags at the bottom of the Markdown file.
- **Accuracy Verification**: Automatically checks the similarity between the original raw extracted text and the final formatted Markdown (alerts if standard similarity drops below 90%). It optimizes large files using bounded comparisons.
- **Performance Tracking**: Measures and prints the exact conversion speed (execution time) per file.
- **Benchmark Evaluation**: Includes a benchmark pipeline that treats the original PDF as ground truth, scores both `2md` and `markitdown` against that same PDF, and exports the results to `benchmark/analysis/comprehensive_evaluation.csv`.
- **Structure Preservation Metrics**: Reports custom Markdown structure metrics for `headers`, `lists`, `tables`, and `images`, plus a combined `MarkdownStructureScore`.
- **Supplementary LLM Judge**: Includes an OpenAI-compatible LLM-as-a-judge script for side-by-side qualitative evaluation of `2md` vs `markitdown`.
- **Flexible Output Paths**:
  - Save to the same directory as the original PDF by default.
  - Save to a specific custom directory.
  - Save to a precise custom file path.
- **Parallel Testing**: Leverages `rayon` to validate and benchmark the entire batch of PDF files concurrently via `cargo test`.
- **Robustness**: Utilizes `anyhow` for strict and comprehensive error handling.
- **Security Check**: Dependency versions are managed strictly via Cargo, and the project supports `cargo-audit` for identifying security vulnerabilities.

## Installation

Ensure you have Rust and Cargo installed. Clone the repository and build the project:

```bash
git clone <repository_url>
cd 2md
cargo build --release
```

## Using as a Rust Crate

This repository also exposes a library crate named `twomd`, so you can use the PDF-to-Markdown logic from your own Rust code.

Add it to `Cargo.toml`.

Using a local path:

```toml
[dependencies]
twomd = { path = "../2md" }
```

Using GitHub directly:

```toml
[dependencies]
twomd = { git = "https://github.com/espseongsm/2md.git" }
```

Minimal example:

```rust
use std::path::Path;
use twomd::pdf::extract_and_format;

fn main() -> anyhow::Result<()> {
    let result = extract_and_format(Path::new("data/sample.pdf"))?;

    println!("Similarity: {:.2}%", result.similarity_score * 100.0);
    println!("{}", result.markdown);

    Ok(())
}
```

If you also want the same output-path behavior as the CLI:

```rust
use std::path::{Path, PathBuf};
use twomd::converter::resolve_output_plan;

fn main() -> anyhow::Result<()> {
    let plan = resolve_output_plan(Path::new("data/sample.pdf"), Some(PathBuf::from("out")))?;
    println!("Markdown path: {}", plan.markdown_path.display());
    println!("Asset dir: {}", plan.asset_dir.display());
    Ok(())
}
```

Current public modules:
- `twomd::pdf`
- `twomd::converter`

## Usage

The primary command requires an input PDF file. You can optionally specify an output directory or exact file path.

**Basic Usage (Saves to same directory):**

```bash
cargo run --release -- data/sample.pdf
```

_Outputs: `data/sample.md`_

**Specify an Output Directory (Saves as `<basename>.md` in directory):**

```bash
cargo run --release -- data/sample.pdf /tmp/
```

_Outputs: `/tmp/sample.md`_

**Specify an Exact Output File Path:**

```bash
cargo run --release -- data/sample.pdf /tmp/custom_name.md
```

_Outputs: `/tmp/custom_name.md`_

## Output Example

When running the tool, you will see output similar to the following:

```
Process started for: data/sample.pdf
Similarity check passed: 98%
Conversion speed: 12.5ms
Successfully saved formatted markdown to: data/sample.md
```

## Benchmarking and Evaluation

The repository includes a benchmark/evaluation pipeline under `benchmark/analysis/evaluate.py`.

Evaluation rule:
- The **original PDF is the ground truth**.
- For each file, the evaluator computes `PDF -> 2md Markdown` and `PDF -> markitdown Markdown`.
- The comparison is then made by looking at the two score sets side by side.

Main metric groups:
- **Semantic / text fidelity**: `Jaccard`, `BLEU`, `Cosine`, `L2`, `SoftCosine`, `BERTScore`, `EditDist`
- **Structure preservation**: `HeaderScore`, `ListScore`, `TableScore`, `ImageScore`, `MarkdownStructureScore`
- **Descriptive output metric**: `Richness`

Metric notes:
- `BLEU` is used here as a precision-oriented metric, so noisy or hallucinated text tends to reduce the score.
- `MarkdownStructureScore` is a custom metric defined as the mean of `HeaderScore`, `ListScore`, `TableScore`, and `ImageScore`.
- Structure scores are based on heuristic PDF structure detection, so they are useful but not perfect.

Generated outputs:
- CSV: `benchmark/analysis/comprehensive_evaluation.csv`
- Report: `benchmark/benchmark_results.md`
- Supplementary LLM judge CSV: `benchmark/analysis/llm_judge_results.csv`
- Supplementary LLM judge JSON: `benchmark/analysis/llm_judge_results.json`

## Key Benchmark Insights

The full benchmark summary is in `benchmark/benchmark_results.md`. The main takeaways are:

- **Speed**: `2md` is the clear runtime winner, averaging about **0.66s** per file versus **9.34s** for `markitdown`, or roughly **14x faster** on the benchmark set.
- **Semantic accuracy**: `2md` performs better on average in `Cosine`, `L2`, `BERTScore`, and `EditDist`, which suggests stronger semantic preservation against the original PDF ground truth.
- **Lexical overlap**: `markitdown` performs better on average in `Jaccard` and `BLEU`, so it retains slightly more direct token- and phrase-level overlap with the extracted PDF text.
- **Structure preservation**: the custom `MarkdownStructureScore` is very close overall, with a slight edge to `2md`; `2md` does better on table and image preservation, while `markitdown` does better on list-count preservation.
- **Supplementary LLM judge**: on the 5 evaluated PDFs, the LLM judge favored `2md` on **3 files** and `markitdown` on **2 files**.

In short: **`2md` is much faster and stronger on average semantic fidelity, while `markitdown` remains competitive on direct lexical overlap and wins on some individual documents.**

## LLM-as-a-Judge

The repository also includes `benchmark/analysis/llm_judge.py` for supplementary judging with an OpenAI-compatible endpoint such as vLLM.

What it does:
- Uses the original PDF as ground truth
- Compares `2md` and `markitdown` side by side
- Scores both outputs on:
  - `faithfulness_to_pdf`
  - `structure_preservation`
  - `table_preservation`
  - `readability`
  - `hallucination_control`
  - `overall`
- Returns a per-file winner plus short evidence

Usage example:

```bash
python3 benchmark/analysis/llm_judge.py \
  --base-url http://40.82.143.121:9008 \
  --api-key "$LLM_JUDGE_API_KEY" \
  --model "$LLM_JUDGE_MODEL"
```

Helpful options:
- `--list-models`: query the endpoint for available model ids
- `--file "<pdf stem>"`: judge a single file
- `--max-chars 4500`: control excerpt size sent to the model

Environment variables:
- `LLM_JUDGE_BASE_URL`
- `LLM_JUDGE_API_KEY`
- `LLM_JUDGE_MODEL`

Notes:
- The judge is supplementary and does not replace the numeric benchmark metrics.
- The script uses excerpts rather than full documents so it stays practical with long PDFs and model context limits.
- A valid API key and model id are required if the endpoint is protected.

## Development and Conventions

- **Module Structure**:
  - `main.rs` is kept lightweight.
  - Core parsing and similarity logic is located in `pdf.rs`.
  - CLI and file path resolution is handled in `converter.rs`.
- **Formatting**: The project adheres to standard Rust formatting (`cargo fmt`).
- **Dependencies**: Managed via `Cargo.toml` and `Cargo.lock`.
