use anyhow::Result;
use lopdf::{Document, Object};

pub fn extract_images(doc: &Document) -> Result<Vec<(u32, String, Vec<u8>)>> {
    let mut extracted_images = Vec::new();

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
                                    // very primitive check.
                                    match stream.decompressed_content() {
                                        Ok(content) => {
                                            extracted_images.push((
                                                page_num,
                                                String::from_utf8_lossy(xobj_name).to_string(),
                                                content,
                                            ));
                                        }
                                        Err(_) => {
                                            // Handle raw if possible
                                            extracted_images.push((
                                                page_num,
                                                String::from_utf8_lossy(xobj_name).to_string(),
                                                stream.content.clone(),
                                            ));
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
    Ok(extracted_images)
}

fn main() {
    let doc = Document::load("data/Agentic_Design_Patterns.pdf").unwrap();
    let imgs = extract_images(&doc).unwrap();
    println!("Found {} images", imgs.len());
    for (page, name, content) in imgs.iter().take(5) {
        println!("Page {} - Image {} - Size {}", page, name, content.len());
    }
}
