use anyhow::{Context, Result};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutputPlan {
    pub markdown_path: PathBuf,
    pub asset_dir: PathBuf,
}

/// Resolve the markdown output path and asset directory from the CLI input.
///
/// The output directory is shared by the Markdown file and extracted images.
/// If `user_output` is:
/// - `None`, the Markdown file is written next to the input file.
/// - an existing directory or a path without an extension, it is treated as a directory.
/// - any other path, it is treated as an explicit file path.
pub fn resolve_output_plan(input_path: &Path, user_output: Option<PathBuf>) -> Result<OutputPlan> {
    let markdown_path = if let Some(user_path) = user_output {
        if user_path.is_dir() || user_path.extension().is_none() {
            let stem = input_path
                .file_stem()
                .context("Input file has no valid name")?;
            let mut new_path = user_path;
            new_path.push(stem);
            new_path.set_extension("md");
            new_path
        } else {
            user_path
        }
    } else {
        let mut new_path = input_path.to_path_buf();
        new_path.set_extension("md");
        new_path
    };

    let asset_dir = markdown_path
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."));

    Ok(OutputPlan {
        markdown_path,
        asset_dir,
    })
}

/// Determines the final output path for the Markdown file.
pub fn determine_output_path(input_path: &Path, user_output: Option<PathBuf>) -> Result<PathBuf> {
    Ok(resolve_output_plan(input_path, user_output)?.markdown_path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolves_default_plan_next_to_input() {
        let input = Path::new("/tmp/source.pdf");
        let plan = resolve_output_plan(input, None).unwrap();

        assert_eq!(plan.markdown_path, PathBuf::from("/tmp/source.md"));
        assert_eq!(plan.asset_dir, PathBuf::from("/tmp"));
    }

    #[test]
    fn treats_missing_extension_path_as_directory() {
        let input = Path::new("/tmp/source.pdf");
        let plan = resolve_output_plan(input, Some(PathBuf::from("/tmp/output"))).unwrap();

        assert_eq!(plan.markdown_path, PathBuf::from("/tmp/output/source.md"));
        assert_eq!(plan.asset_dir, PathBuf::from("/tmp/output"));
    }

    #[test]
    fn preserves_explicit_file_path() {
        let input = Path::new("/tmp/source.pdf");
        let plan =
            resolve_output_plan(input, Some(PathBuf::from("/tmp/custom/output.md"))).unwrap();

        assert_eq!(plan.markdown_path, PathBuf::from("/tmp/custom/output.md"));
        assert_eq!(plan.asset_dir, PathBuf::from("/tmp/custom"));
    }
}
