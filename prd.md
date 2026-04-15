# 2MD PRD

The goal is to build a module that convert any document into a markdown file.
The language is Rust for memory safety and speed.

## Features

- Convert below document formats into markdown
  - pdf
- Multiple files can be converted at the same time, using parallel processing.
- Converted documents should be saved in the same directory as the original document. The extension should be `.md`.
- However, if the path is given as an argument, the document should be saved in the given path.
- Tables in the document should be converted into markdown tables.
- Images in the document should be extracted and saved in the same directory as the original document. The extension should be `.png`. And the images should be in the same location in the markdown file.
- Hyperlink in the document should be converted into markdown hyperlink.
- The converted markdown file should be well-formatted and easy to read.
- **Performance & Accuracy Goals**:
  - **Conversion Speed**: Target a significant lead over existing Python-based solutions such as MarkItDown.
  - **PDF-Ground-Truth Evaluation**: The original PDF is the ground truth. Evaluation should compare `PDF -> 2md Markdown` and `PDF -> markitdown Markdown`, then compare those metric values side by side.
  - **Semantic Fidelity**: Ensure high semantic similarity to the original PDF using embedding-based metrics such as `Cosine`, `L2`, `SoftCosine`, and `BERTScore`.
  - **Lexical Fidelity**: Measure direct textual overlap using `Jaccard`, `BLEU`, and `EditDist`.
  - **Markdown Structure Preservation**: Measure how well tables, headers, lists, and images are preserved using custom structure metrics.
  - **Supplementary LLM Judgment**: Add an LLM-as-a-judge layer for qualitative comparison of `2md` vs `markitdown`, but keep numeric PDF-ground-truth metrics as the primary benchmark.
- Please check the similarity of the converted markdown file with the original document using the benchmark pipeline in `benchmark/analysis/evaluate.py`.
- Please check the conversion speed per file.

## Evaluation Metrics

- **Semantic / textual metrics**
  - `Jaccard`: unique-token overlap between PDF text and Markdown text
  - `BLEU`: precision-oriented n-gram overlap, useful for detecting hallucinated or noisy output
  - `Cosine`: embedding cosine similarity
  - `L2`: embedding distance
  - `SoftCosine`: embedding-aware token similarity
  - `BERTScore`: contextual semantic similarity
  - `EditDist`: normalized Levenshtein similarity
- **Structure / layout metrics**
  - `Struct`: header-set overlap between PDF-detected headers and Markdown headers
  - `HeaderScore`: normalized count similarity for headings
  - `ListScore`: normalized count similarity for lists
  - `TableScore`: normalized count similarity for tables
  - `ImageScore`: normalized count similarity for images
  - `MarkdownStructureScore`: mean of `HeaderScore`, `ListScore`, `TableScore`, and `ImageScore`
  - `Richness`: output-side Markdown structure count, useful as a descriptive metric but not a direct PDF-ground-truth score

## Benchmark Outputs

- Evaluation CSV: `benchmark/analysis/comprehensive_evaluation.csv`
- Human-readable benchmark summary: `benchmark/benchmark_results.md`
- Benchmark evaluator: `benchmark/analysis/evaluate.py`
- Supplementary LLM judge CSV: `benchmark/analysis/llm_judge_results.csv`
- Supplementary LLM judge JSON: `benchmark/analysis/llm_judge_results.json`
- Supplementary LLM judge script: `benchmark/analysis/llm_judge.py`

## Data

- In the directory of `data` folder, there are some sample documents.

## Code Conventions

- main.rs should be clean and neat.
- README.md should include all the features and updates.
- `cargo fmt` should be used for code formatting.
- `anyhow` should be used for strict error handling.
- `main.rs` should be kept light and logic should be separated into modules.
- Cargo should be used to manage the project.
- `cargo-audit` should be used to check for security vulnerabilities in dependencies.
- `Cargo.toml` and `Cargo.lock` should be used to manage dependency versions.

## Test

- Please test the code with the sample documents in the `data` folder in a parallel manner.
- every feature should be validated.
