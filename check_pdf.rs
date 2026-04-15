use pdf_extract::extract_text_by_pages;
use std::path::Path;

fn main() {
    let path = Path::new("data/Agentic_Design_Patterns.pdf");
    match extract_text_by_pages(path) {
        Ok(pages) => {
            println!("Got {} pages", pages.len());
        }
        Err(e) => {
            println!("Error: {}", e);
        }
    }
}
