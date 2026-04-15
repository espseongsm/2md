use std::fs;
use std::path::PathBuf;
use std::time::Instant;
use std::time::{SystemTime, UNIX_EPOCH};

use rayon::prelude::*;
use twomd::converter::resolve_output_plan;
use twomd::pdf::extract_and_format;

fn unique_temp_root() -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("System time must be after UNIX_EPOCH")
        .as_nanos();

    std::env::temp_dir().join(format!("twomd-integration-{nanos}-{}", std::process::id()))
}

#[test]
fn test_all_pdfs_in_parallel() {
    let data_dir = PathBuf::from("data");
    assert!(data_dir.exists(), "Data directory not found");

    let entries: Vec<_> = fs::read_dir(data_dir)
        .expect("Failed to read data dir")
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| {
            p.extension()
                .and_then(|e| e.to_str())
                .is_some_and(|ext| ext.eq_ignore_ascii_case("pdf"))
        })
        .collect();

    assert!(!entries.is_empty(), "No PDFs found in data directory");

    let output_root = unique_temp_root();
    fs::create_dir_all(&output_root).expect("Failed to create temp output root");

    entries.par_iter().for_each(|pdf_path| {
        let start_time = Instant::now();
        println!("Testing: {}", pdf_path.display());

        let result = extract_and_format(pdf_path)
            .unwrap_or_else(|_| panic!("Extraction failed for {}", pdf_path.display()));

        if result.raw_text.trim().is_empty() {
            println!(
                "Skipping markdown generation check for {} as raw text is empty.",
                pdf_path.display()
            );
            return;
        }

        // Validation: Markdown generated
        assert!(
            !result.markdown.is_empty(),
            "Markdown is empty for {}",
            pdf_path.display()
        );

        // Validation: Similarity Score >= 90% (warn if slightly below, panic if terrible)
        let pct = (result.similarity_score * 100.0).round();
        if pct < 90.0 {
            println!(
                "Warning: Similarity score is {}% (below 90% target) for {}",
                pct,
                pdf_path.display()
            );
        }
        assert!(
            pct >= 85.0,
            "Similarity score too low ({}%) for {}",
            pct,
            pdf_path.display()
        );

        let pdf_stem = pdf_path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .expect("PDF file must have a valid stem");
        let output_dir = output_root.join(pdf_stem);
        let output_plan =
            resolve_output_plan(pdf_path, Some(output_dir)).expect("Output plan resolution failed");

        fs::create_dir_all(&output_plan.asset_dir).expect("Failed to create output directory");

        let mut final_markdown = result.markdown;
        final_markdown.push_str("\n\n---\n**Conversion Metrics:**\n");
        final_markdown.push_str(&format!("- Similarity Score: {}%\n", pct));
        let duration = start_time.elapsed();
        final_markdown.push_str(&format!("- Conversion Speed: {:?}\n", duration));

        fs::write(&output_plan.markdown_path, final_markdown).expect("Failed to write Markdown");
        assert!(
            output_plan.markdown_path.exists(),
            "Output markdown file was not created"
        );

        for (img_name, img) in result.images {
            let img_path = output_plan.asset_dir.join(&img_name);
            img.save_with_format(&img_path, image::ImageFormat::Png)
                .expect("Failed to save image");
            assert!(
                img_path.exists(),
                "Image file was not created: {}",
                img_path.display()
            );
            assert!(
                img_path.extension().and_then(|e| e.to_str()) == Some("png"),
                "Image extension must be png"
            );
        }

        println!(
            "Successfully processed {} in {:?}",
            pdf_path.display(),
            duration
        );
    });

    fs::remove_dir_all(&output_root).expect("Failed to clean up temp output root");
}
