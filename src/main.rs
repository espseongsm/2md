use anyhow::{Context, Result};
use clap::Parser;
use std::path::PathBuf;
use std::time::Instant;

use twomd::converter::resolve_output_plan;
use twomd::pdf::extract_and_format;

/// Convert PDF documents to Markdown
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Input PDF file path
    input_file: PathBuf,

    /// Optional output file or directory path (defaults to same directory as input)
    output_path: Option<PathBuf>,
}

fn main() -> Result<()> {
    let args = Args::parse();

    // 1. Validate Input
    if !args.input_file.is_file() {
        anyhow::bail!(
            "Input path must be an existing file: {}",
            args.input_file.display()
        );
    }

    if !args
        .input_file
        .extension()
        .and_then(|e| e.to_str())
        .is_some_and(|ext| ext.eq_ignore_ascii_case("pdf"))
    {
        anyhow::bail!("Input file must be a PDF");
    }

    let output_plan = resolve_output_plan(&args.input_file, args.output_path)?;
    std::fs::create_dir_all(&output_plan.asset_dir).with_context(|| {
        format!(
            "Failed to prepare output directory {}",
            output_plan.asset_dir.display()
        )
    })?;

    println!("Process started for: {}", args.input_file.display());

    // 2. Measure Conversion Speed
    let start_time = Instant::now();
    let extraction_result = extract_and_format(&args.input_file)
        .with_context(|| format!("Failed to process PDF: {}", args.input_file.display()))?;
    let duration = start_time.elapsed();

    // 3. Document Processing and Validation
    let formatted_similarity_pct = (extraction_result.similarity_score * 100.0).round();

    if formatted_similarity_pct < 90.0 {
        println!(
            "Warning: Similarity check failed. The formatted markdown represents the original poorly ({formatted_similarity_pct}%)."
        );
    } else {
        println!("Similarity check passed: {}%", formatted_similarity_pct);
    }

    println!("Conversion speed: {:?}", duration);

    // 4. Save to Disk
    let mut final_markdown = extraction_result.markdown;
    final_markdown.push_str("\n\n---\n");
    final_markdown.push_str("**Conversion Metrics:**\n");
    final_markdown.push_str(&format!(
        "- Similarity Score: {}%\n",
        formatted_similarity_pct
    ));
    final_markdown.push_str(&format!("- Conversion Speed: {:?}\n", duration));

    std::fs::write(&output_plan.markdown_path, final_markdown).with_context(|| {
        format!(
            "Failed to write output to {}",
            output_plan.markdown_path.display()
        )
    })?;

    println!(
        "Successfully saved formatted markdown to: {}",
        output_plan.markdown_path.display()
    );

    for (img_name, img) in extraction_result.images {
        let img_path = output_plan.asset_dir.join(&img_name);
        if let Err(e) = img.save_with_format(&img_path, image::ImageFormat::Png) {
            eprintln!("Warning: Failed to save {}: {}", img_path.display(), e);
        } else {
            println!("Saved image: {}", img_path.display());
        }
    }

    Ok(())
}
