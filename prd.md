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
  - **Conversion Speed**: Target a significant lead over existing Python-based solutions (e.g., MarkItDown). Benchmark showed `2md` is ~14x faster on average.
  - **Semantic Fidelity**: Ensure a high semantic similarity score (Target > 0.90) compared to the original PDF ground truth using embedding-based metrics.
  - **Token Recall**: Maintain high text recovery (Target > 90%) to ensure no critical information is lost during conversion.
- Please check the similarity of the converted markdown file with the original document. The similarity should be above 90%. Randomly select 5,000 words and check the similarity.
- Please check the conversion speed per file.

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
