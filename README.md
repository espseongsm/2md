# 2md

A fast, memory-safe CLI tool written in Rust to convert PDF documents into well-formatted Markdown files.

## Features

- **PDF to Markdown Conversion**: Extracts text from PDFs and intelligently formats it into readable Markdown, removing unnecessary line breaks and establishing paragraphs.
- **Table Extraction**: Intelligent splitting logic parses PDF tabular data and translates it into well-formed Markdown tables.
- **Image Extraction**: Discovers embedded images directly within the PDF, extracts and saves them locally as `.png` files, and automatically injects image tags at the bottom of the Markdown file.
- **Accuracy Verification**: Automatically checks the similarity between the original raw extracted text and the final formatted Markdown (alerts if standard similarity drops below 90%). It optimizes large files using bounded comparisons.
- **Performance Tracking**: Measures and prints the exact conversion speed (execution time) per file.
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

## Development and Conventions

- **Module Structure**:
  - `main.rs` is kept lightweight.
  - Core parsing and similarity logic is located in `pdf.rs`.
  - CLI and file path resolution is handled in `converter.rs`.
- **Formatting**: The project adheres to standard Rust formatting (`cargo fmt`).
- **Dependencies**: Managed via `Cargo.toml` and `Cargo.lock`.
