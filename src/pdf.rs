use anyhow::{Context, Result};
use image::DynamicImage;
use lopdf::{Document, Object};
use pdf_extract::extract_text;
use std::collections::HashSet;
use std::path::Path;

pub struct ExtractionResult {
    pub raw_text: String,
    pub markdown: String,
    pub similarity_score: f64,
    pub images: Vec<(String, DynamicImage)>,
}

pub fn extract_and_format(path: &Path) -> Result<ExtractionResult> {
    // 1. Text
    let raw_text = extract_text(path).context("Failed to extract text from PDF")?;

    // 2. Images via lopdf
    let mut images = Vec::new();
    let mut image_markers = String::new();

    if let Ok(doc) = Document::load(path) {
        for (page_num, page_id) in doc.get_pages() {
            if let Ok(Object::Dictionary(page_dict)) = doc.get_object(page_id) {
                if let Ok(Object::Dictionary(resources)) = page_dict.get(b"Resources") {
                    if let Ok(Object::Dictionary(xobjects)) = resources.get(b"XObject") {
                        for (xobj_name, xobj_ref) in xobjects.iter() {
                            if let Object::Reference(ref_id) = xobj_ref {
                                if let Ok(Object::Stream(stream)) = doc.get_object(*ref_id) {
                                    let dict = &stream.dict;
                                    if dict
                                        .get(b"Subtype")
                                        .and_then(|obj| obj.as_name())
                                        .unwrap_or(b"")
                                        == b"Image"
                                    {
                                        let base_name =
                                            path.file_stem().unwrap_or_default().to_string_lossy();
                                        // The extension will be assigned as png explicitly by the image encoder
                                        let img_name = format!(
                                            "{}_page{}_{}.png",
                                            base_name,
                                            page_num,
                                            String::from_utf8_lossy(xobj_name)
                                        );

                                        let content = stream
                                            .decompressed_content()
                                            .unwrap_or_else(|_| stream.content.clone());
                                        if let Ok(dynamic_image) = image::load_from_memory(&content)
                                        {
                                            images.push((img_name.clone(), dynamic_image));
                                            image_markers
                                                .push_str(&format!("\n![Image]({})\n", img_name));
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // 3. Format the text
    let mut markdown = format_markdown(&raw_text);
    let similarity_score = calculate_similarity_score(&raw_text, &markdown);

    // Append images
    if !image_markers.is_empty() {
        markdown.push_str("\n\n## Extracted Images\n");
        markdown.push_str(&image_markers);
    }

    Ok(ExtractionResult {
        raw_text,
        markdown,
        similarity_score,
        images,
    })
}

/// Basic formatting rules to generate clean Markdown from raw extracted PDF text, including a table heuristic.
fn format_markdown(raw_text: &str) -> String {
    let mut formatted = String::with_capacity(raw_text.len());
    let mut last_line_empty = false;
    let mut in_table = false;

    for line in raw_text.lines() {
        let trimmed = line.trim();

        if trimmed.is_empty() {
            if !last_line_empty {
                formatted.push_str("\n\n");
                last_line_empty = true;
            }
            in_table = false;
        } else {
            let chunks = split_table_columns(trimmed);
            let is_likely_table_row = is_likely_table_row(&chunks);

            if is_likely_table_row {
                if !in_table {
                    formatted.push_str("\n| ");
                    formatted.push_str(&chunks.join(" | "));
                    formatted.push_str(" |\n|");
                    for _ in 0..chunks.len() {
                        formatted.push_str("---|");
                    }
                    formatted.push_str("\n");
                    in_table = true;
                } else {
                    formatted.push_str("| ");
                    formatted.push_str(&chunks.join(" | "));
                    formatted.push_str(" |\n");
                }
                last_line_empty = false;
                continue;
            } else {
                in_table = false;
            }

            if should_join_with_previous(&formatted, trimmed) {
                formatted.push(' ');
            } else if !formatted.is_empty() && !formatted.ends_with('\n') {
                formatted.push('\n');
            }

            formatted.push_str(trimmed);
            last_line_empty = false;
        }
    }

    formatted
}

fn calculate_similarity_score(raw_text: &str, markdown: &str) -> f64 {
    let raw_tokens = normalize_for_similarity(raw_text);
    if raw_tokens.is_empty() {
        return 1.0;
    }

    let markdown_tokens = normalize_for_similarity(markdown);
    let markdown_words: HashSet<&str> = markdown_tokens.iter().map(String::as_str).collect();
    let sample_size = raw_tokens.len().min(5000);

    if sample_size == 0 {
        return 1.0;
    }

    let matches = evenly_spaced_indices(raw_tokens.len(), sample_size)
        .into_iter()
        .filter(|index| markdown_words.contains(raw_tokens[*index].as_str()))
        .count();

    matches as f64 / sample_size as f64
}

fn normalize_for_similarity(text: &str) -> Vec<String> {
    let mut normalized = Vec::new();
    let mut current = String::new();

    for ch in text.chars() {
        if ch.is_alphanumeric() {
            for lower in ch.to_lowercase() {
                current.push(lower);
            }
        } else if !current.is_empty() {
            normalized.push(std::mem::take(&mut current));
        }
    }

    if !current.is_empty() {
        normalized.push(current);
    }

    normalized
}

fn evenly_spaced_indices(len: usize, sample_size: usize) -> Vec<usize> {
    if sample_size >= len {
        return (0..len).collect();
    }

    (0..sample_size).map(|i| i * len / sample_size).collect()
}

fn split_table_columns(line: &str) -> Vec<String> {
    let mut columns = Vec::new();
    let mut current = String::new();
    let mut whitespace_run = 0usize;

    for ch in line.trim().chars() {
        if ch.is_whitespace() {
            whitespace_run += 1;
            continue;
        }

        if whitespace_run >= 3 {
            let trimmed = current.trim();
            if !trimmed.is_empty() {
                columns.push(trimmed.to_string());
            }
            current.clear();
        } else if whitespace_run > 0 {
            current.extend(std::iter::repeat(' ').take(whitespace_run));
        }

        whitespace_run = 0;
        current.push(ch);
    }

    if whitespace_run >= 3 {
        let trimmed = current.trim();
        if !trimmed.is_empty() {
            columns.push(trimmed.to_string());
        }
    } else if whitespace_run > 0 {
        current.extend(std::iter::repeat(' ').take(whitespace_run));
    }

    let trimmed = current.trim();
    if !trimmed.is_empty() {
        columns.push(trimmed.to_string());
    }

    columns
}

fn is_likely_table_row(columns: &[String]) -> bool {
    if columns.len() < 2 {
        return false;
    }

    let column_lengths: Vec<usize> = columns.iter().map(|c| c.trim().chars().count()).collect();
    if column_lengths.iter().any(|len| *len == 0 || *len > 40) {
        return false;
    }

    if columns.len() >= 3 {
        return true;
    }

    column_lengths.iter().all(|len| *len <= 30)
}

fn should_join_with_previous(formatted: &str, current_line: &str) -> bool {
    let previous_line = formatted.rsplit('\n').next().unwrap_or("").trim_end();
    if previous_line.is_empty()
        || is_structural_line(previous_line)
        || is_structural_line(current_line)
    {
        return false;
    }

    if ends_with_sentence_boundary(previous_line) || previous_line.chars().count() < 40 {
        return false;
    }

    matches!(
        current_line.chars().next(),
        Some(ch) if ch.is_lowercase() || ch.is_numeric() || matches!(ch, '(' | '[' | '"' | '\'')
    )
}

fn is_structural_line(line: &str) -> bool {
    is_bullet_line(line) || is_numbered_list_line(line) || is_heading_like(line)
}

fn is_bullet_line(line: &str) -> bool {
    let trimmed = line.trim_start();
    trimmed.starts_with("- ")
        || trimmed.starts_with("* ")
        || trimmed.starts_with("+ ")
        || trimmed.starts_with('•')
}

fn is_numbered_list_line(line: &str) -> bool {
    let trimmed = line.trim_start();
    let mut chars = trimmed.chars().peekable();
    let mut digits = 0usize;

    while matches!(chars.peek(), Some(ch) if ch.is_ascii_digit()) {
        digits += 1;
        chars.next();
    }

    if digits == 0 {
        return false;
    }

    match chars.next() {
        Some('.') | Some(')') => matches!(chars.peek(), Some(' ') | Some('\t')),
        _ => false,
    }
}

fn is_heading_like(line: &str) -> bool {
    let trimmed = line.trim();
    if trimmed.is_empty() || trimmed.len() > 45 || ends_with_sentence_boundary(trimmed) {
        return false;
    }

    let word_count = trimmed.split_whitespace().count();
    if word_count == 0 || word_count > 6 {
        return false;
    }

    trimmed
        .chars()
        .next()
        .map(|ch| ch.is_uppercase())
        .unwrap_or(false)
}

fn ends_with_sentence_boundary(line: &str) -> bool {
    matches!(
        line.chars().rev().find(|ch| !ch.is_whitespace()),
        Some('.') | Some('!') | Some('?') | Some(':') | Some(';')
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn similarity_is_deterministic_and_normalized() {
        let first = calculate_similarity_score("Hello, world!", "# hello world");
        let second = calculate_similarity_score("Hello, world!", "# hello world");

        assert_eq!(first, second);
        assert!((first - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn similarity_score_is_bounded_for_large_inputs() {
        let raw_text = (0..10_000)
            .map(|index| format!("word{index}"))
            .collect::<Vec<_>>()
            .join(" ");
        let markdown = raw_text.clone();

        assert!((calculate_similarity_score(&raw_text, &markdown) - 1.0).abs() < f64::EPSILON);
        assert_eq!(evenly_spaced_indices(10_000, 5_000).len(), 5_000);
    }

    #[test]
    fn splits_table_rows_on_three_plus_spaces() {
        let columns = split_table_columns("Name   Role    Status");

        assert_eq!(columns, vec!["Name", "Role", "Status"]);
        assert!(is_likely_table_row(&columns));
    }

    #[test]
    fn format_markdown_preserves_structural_lines() {
        let input = "Executive Summary\nnext line\n- First item\ncontinued item\n1. Second item\ncontinued second item\nParagraph with a soft wrap that should join\nacross the next line.";

        let formatted = format_markdown(input);

        assert!(formatted.contains("Executive Summary\nnext line"));
        assert!(formatted.contains("- First item\ncontinued item"));
        assert!(formatted.contains("1. Second item\ncontinued second item"));
        assert!(
            formatted.contains("Paragraph with a soft wrap that should join across the next line.")
        );
    }
}
