import os
import re
import numpy as np
import unicodedata
from pathlib import Path
from typing import List, Tuple, Dict, Set
import pandas as pd
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
import nltk
from bert_score import BERTScorer
from rapidfuzz.distance import Levenshtein
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction

# Ensure necessary NLTK resources are downloaded
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab')

class TextCleaner:
    """Utility class to handle text normalization and markdown stripping."""

    @staticmethod
    def clean(text: str) -> str:
        """Removes markdown formatting to focus on raw semantic content."""
        text = re.sub(r'#+\s+', '', text)
        text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
        text = re.sub(r'(\*|_)(.*?)\1', r'\2', text)
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        return text.strip()

    @staticmethod
    def extract_md_headers(text: str) -> List[str]:
        """Extracts all markdown headers."""
        return re.findall(r'^#+\s+.*$', text, re.MULTILINE)

    @staticmethod
    def extract_md_structure_counts(text: str) -> Dict[str, int]:
        """Counts Markdown structures used for layout preservation scoring."""
        table_separator_pattern = r'^\s*\|?(?:\s*:?-{3,}:?\s*\|)+(?:\s*:?-{3,}:?\s*)?\s*$'
        return {
            "headers": len(re.findall(r'^#+\s+', text, re.MULTILINE)),
            "lists": len(re.findall(r'^\s*([-*+]|[0-9]+\.)\s+', text, re.MULTILINE)),
            "tables": len(re.findall(table_separator_pattern, text, re.MULTILINE)),
            "images": len(re.findall(r'!\[.*?\]\(.*?\)', text)),
        }

    @staticmethod
    def count_md_elements(text: str) -> Dict[str, int]:
        """Counts structural elements in markdown to measure richness."""
        return {
            "tables": len(re.findall(r'\|.*\|', text)),
            "lists": len(re.findall(r'^\s*([-*+]|\d+\.)\s+', text, re.MULTILINE)),
            "images": len(re.findall(r'!\[.*?\]\(.*?\)', text)),
            "headers": len(re.findall(r'^#+\s+', text, re.MULTILINE))
        }

class MetricScorer:
    """Pure mathematical functions for calculating similarity metrics."""

    @staticmethod
    def _pairwise_similarity_sum(
        embeddings_a: np.ndarray,
        embeddings_b: np.ndarray,
        batch_size: int = 256,
    ) -> float:
        """Sums cosine similarities in chunks to avoid giant unstable matrices."""
        total = 0.0
        for start in range(0, len(embeddings_a), batch_size):
            chunk = embeddings_a[start:start + batch_size]
            with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                pairwise = chunk @ embeddings_b.T
            pairwise = np.clip(
                np.nan_to_num(pairwise, nan=0.0, posinf=0.0, neginf=0.0),
                -1.0,
                1.0,
            )
            total += float(pairwise.sum(dtype=np.float64))
        return total

    @staticmethod
    def calculate_jaccard(set1: Set, set2: Set) -> float:
        """Calculates Jaccard similarity between two sets."""
        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0
        return len(set1 & set2) / len(set1 | set2)

    @staticmethod
    def calculate_token_jaccard(text1: str, text2: str) -> float:
        """Calculates Jaccard similarity between word sets of two documents."""
        words1 = set(re.findall(r'\w+', text1.lower()))
        words2 = set(re.findall(r'\w+', text2.lower()))
        return MetricScorer.calculate_jaccard(words1, words2)

    @staticmethod
    def calculate_count_similarity(expected: int, observed: int) -> float:
        """Compares two structure counts on a normalized 0..1 scale."""
        if expected == 0 and observed == 0:
            return 1.0
        return max(0.0, 1.0 - (abs(expected - observed) / max(expected, observed, 1)))

    @staticmethod
    def calculate_markdown_structure_scores(
        pdf_counts: Dict[str, int],
        md_counts: Dict[str, int],
    ) -> Dict[str, float]:
        """Scores how well Markdown preserves PDF structure counts."""
        component_scores = {
            "HeaderScore": MetricScorer.calculate_count_similarity(pdf_counts["headers"], md_counts["headers"]),
            "ListScore": MetricScorer.calculate_count_similarity(pdf_counts["lists"], md_counts["lists"]),
            "TableScore": MetricScorer.calculate_count_similarity(pdf_counts["tables"], md_counts["tables"]),
            "ImageScore": MetricScorer.calculate_count_similarity(pdf_counts["images"], md_counts["images"]),
        }
        component_scores["MarkdownStructureScore"] = float(np.mean(list(component_scores.values())))
        return component_scores

    @staticmethod
    def calculate_soft_cosine(text1: str, text2: str, model: SentenceTransformer) -> float:
        """
        Calculates Soft Cosine Similarity using word-level embeddings.
        This accounts for synonyms by using the similarity matrix of words.
        """
        words1 = list(set(re.findall(r'\w+', text1.lower())))
        words2 = list(set(re.findall(r'\w+', text2.lower())))

        if not words1 or not words2:
            return 0.0

        all_words = list(set(words1 + words2))
        word_embeddings = np.nan_to_num(
            np.asarray(model.encode(all_words), dtype=np.float32),
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )
        word_to_idx = {word: i for i, word in enumerate(all_words)}

        try:
            row_norms = np.linalg.norm(word_embeddings, axis=1, keepdims=True)
            row_norms[row_norms == 0] = 1.0
            normalized_embeddings = np.nan_to_num(
                word_embeddings / row_norms,
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )

            embeddings1 = normalized_embeddings[[word_to_idx[w] for w in words1]]
            embeddings2 = normalized_embeddings[[word_to_idx[w] for w in words2]]

            numerator = MetricScorer._pairwise_similarity_sum(embeddings1, embeddings2)
            denom_part1 = MetricScorer._pairwise_similarity_sum(embeddings1, embeddings1)
            denom_part2 = MetricScorer._pairwise_similarity_sum(embeddings2, embeddings2)
            denominator = np.sqrt(denom_part1 * denom_part2)

            if denominator == 0 or np.isnan(denominator):
                return 0.0

            result = float(numerator / denominator)
            return result if not np.isnan(result) and not np.isinf(result) else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def calculate_bertscore(text1: str, text2: str, scorer: BERTScorer) -> float:
        """Calculates BERTScore F1 between two texts."""
        if not text1 or not text2:
            return 0.0
        _, _, F1 = scorer.score([text1], [text2])
        return float(F1[0])

    @staticmethod
    def calculate_edit_distance(text1: str, text2: str) -> float:
        """Calculates normalized Levenshtein similarity (1.0 = exact match)."""
        return float(Levenshtein.normalized_similarity(text1, text2))

    @staticmethod
    def calculate_bleu(text1: str, text2: str) -> float:
        """Calculates BLEU score using nltk."""
        if not text1 or not text2:
            return 0.0
        ref = [nltk.word_tokenize(text1.lower())]
        cand = nltk.word_tokenize(text2.lower())
        return float(sentence_bleu(ref, cand, smoothing_function=SmoothingFunction().method1))

class Evaluator:
    """Orchestrator for the PDF-to-Markdown evaluation pipeline."""

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', bert_model_type: str = 'roberta-large'):
        print(f"Loading embedding model ({model_name})...")
        self.model = SentenceTransformer(model_name)
        print(f"Loading BERTScore model ({bert_model_type})...")
        self.bert_scorer = BERTScorer(model_type=bert_model_type, lang="en", rescale_with_baseline=True)
        self.cleaner = TextCleaner()
        self.metrics = MetricScorer()

    @staticmethod
    def normalize_for_matching(text: str) -> str:
        """Normalizes filenames so Unicode-equivalent names match reliably."""
        normalized = unicodedata.normalize("NFC", text).casefold()
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    @staticmethod
    def count_pdf_table_blocks(page_text: str) -> int:
        """Heuristically counts table-like blocks from extracted PDF text."""
        block_count = 0
        in_block = False

        for raw_line in page_text.split('\n'):
            line = raw_line.strip()
            if not line:
                in_block = False
                continue

            columns = [part.strip() for part in re.split(r'(?: {2,}|\t)+', line) if part.strip()]
            is_table_like = line.count('|') >= 2 or len(columns) >= 3

            if is_table_like and not in_block:
                block_count += 1
            in_block = is_table_like

        return block_count

    @staticmethod
    def count_pdf_images(page) -> int:
        """Counts image XObjects on a PDF page when available."""
        try:
            return len(page.images)
        except Exception:
            return 0

    def extract_pdf_data(self, pdf_path: Path) -> Tuple[str, List[str], Dict[str, int]]:
        """Extracts PDF text plus heuristic structure counts used as ground truth."""
        try:
            reader = PdfReader(pdf_path)
            text_pages = []
            headers = []
            pdf_lists = 0
            pdf_tables = 0
            pdf_images = 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text_pages.append(page_text)
                pdf_lists += len(re.findall(r'^\s*(?:[-*•·]|\d+[.)])\s+', page_text, re.MULTILINE))
                pdf_tables += self.count_pdf_table_blocks(page_text)
                pdf_images += self.count_pdf_images(page)

                # Heuristic: Short lines that are ALL CAPS or Title Case
                for line in page_text.split('\n'):
                    line = line.strip()
                    if line and len(line) <= 100 and (line.isupper() or line.istitle()):
                        headers.append(line)

            pdf_structure_counts = {
                "headers": len(headers),
                "lists": pdf_lists,
                "tables": pdf_tables,
                "images": pdf_images,
            }
            return "\n".join(text_pages).strip(), headers, pdf_structure_counts
        except Exception as e:
            print(f"Error reading PDF {pdf_path}: {e}")
            return "", [], {}

    def match_markdown_files(self, file_id: str, benchmark_dir: Path) -> Dict[str, Path]:
        """Matches 2md and markitdown outputs for a given PDF stem."""
        matches = {}
        normalized_file_id = self.normalize_for_matching(file_id)
        all_mds = list(benchmark_dir.glob("*.md"))
        for md_file in all_mds:
            normalized_stem = self.normalize_for_matching(md_file.stem)
            if normalized_file_id in normalized_stem:
                if "_markitdown_" in normalized_stem:
                    matches["markitdown"] = md_file
                elif "_2md_" in normalized_stem:
                    matches["2md"] = md_file
        return matches

    def evaluate_file(self, file_id: str, pdf_path: Path, md_files: Dict[str, Path]) -> Dict:
        """Computes PDF-ground-truth metrics for one PDF and its Markdown outputs."""
        # 1. Ground Truth Processing
        gt_text, gt_headers, pdf_structure_counts = self.extract_pdf_data(pdf_path)
        if not gt_text:
            return {}

        clean_gt = self.cleaner.clean(gt_text)
        gt_embedding = self.model.encode([clean_gt])[0]
        gt_header_set = set(gt_headers)

        results = {
            "File": file_id,
            "PDF_Headers": pdf_structure_counts["headers"],
            "PDF_Lists": pdf_structure_counts["lists"],
            "PDF_Tables": pdf_structure_counts["tables"],
            "PDF_Images": pdf_structure_counts["images"],
        }

        # 2. Tool-specific Evaluation
        for tool in ["2md", "markitdown"]:
            if tool not in md_files:
                continue

            with open(md_files[tool], 'r', encoding='utf-8') as f:
                md_text = f.read()

            clean_md = self.cleaner.clean(md_text)
            md_embedding = self.model.encode([clean_md])[0]
            md_headers = self.cleaner.extract_md_headers(md_text)
            md_header_set = set(md_headers)
            md_structure_counts = self.cleaner.extract_md_structure_counts(md_text)
            structure_scores = self.metrics.calculate_markdown_structure_scores(
                pdf_structure_counts,
                md_structure_counts,
            )

            # Structural / output-format metrics
            struct_sim = self.metrics.calculate_jaccard(gt_header_set, md_header_set)
            richness = self.cleaner.count_md_elements(md_text)
            richness_score = sum(richness.values())

            # PDF-ground-truth lexical metrics
            text_jaccard = self.metrics.calculate_token_jaccard(clean_gt, clean_md)
            bleu_sim = self.metrics.calculate_bleu(clean_gt, clean_md)

            # PDF-ground-truth semantic and edit-distance metrics
            cos_sim = cosine_similarity([gt_embedding], [md_embedding])[0][0]
            l2_dist = euclidean_distances([gt_embedding], [md_embedding])[0][0]
            soft_sim = self.metrics.calculate_soft_cosine(clean_gt, clean_md, self.model)
            bert_sim = self.metrics.calculate_bertscore(clean_gt, clean_md, self.bert_scorer)
            edit_sim = self.metrics.calculate_edit_distance(clean_gt, clean_md)

            # Append to results with tool prefix
            results[f"{tool}_Struct"] = round(struct_sim, 3)
            results[f"{tool}_Richness"] = richness_score
            results[f"{tool}_MdHeaders"] = md_structure_counts["headers"]
            results[f"{tool}_MdLists"] = md_structure_counts["lists"]
            results[f"{tool}_MdTables"] = md_structure_counts["tables"]
            results[f"{tool}_MdImages"] = md_structure_counts["images"]
            results[f"{tool}_HeaderScore"] = round(structure_scores["HeaderScore"], 3)
            results[f"{tool}_ListScore"] = round(structure_scores["ListScore"], 3)
            results[f"{tool}_TableScore"] = round(structure_scores["TableScore"], 3)
            results[f"{tool}_ImageScore"] = round(structure_scores["ImageScore"], 3)
            results[f"{tool}_MarkdownStructureScore"] = round(structure_scores["MarkdownStructureScore"], 3)
            results[f"{tool}_Jaccard"] = round(text_jaccard, 3)
            results[f"{tool}_BLEU"] = round(bleu_sim, 3)
            results[f"{tool}_Cosine"] = round(float(cos_sim), 3)
            results[f"{tool}_L2"] = round(float(l2_dist), 3)
            results[f"{tool}_SoftCosine"] = round(soft_sim, 3)
            results[f"{tool}_BERTScore"] = round(bert_sim, 3)
            results[f"{tool}_EditDist"] = round(edit_sim, 3)

        return results

    def run_all(self, data_dir: Path, benchmark_dir: Path):
        """Main execution loop."""
        all_pdfs = list(data_dir.glob("*.pdf"))
        final_results = []

        for pdf_path in all_pdfs:
            file_id = pdf_path.stem
            print(f"Analyzing {file_id}...")

            md_files = self.match_markdown_files(file_id, benchmark_dir)
            if not md_files:
                print(f"  Skipping: No matching markdown files found.")
                continue

            res = self.evaluate_file(file_id, pdf_path, md_files)
            if res:
                final_results.append(res)

        # Create DataFrame and Export
        df = pd.DataFrame(final_results)

        print("\n" + "="*50)
        print("COMPREHENSIVE EVALUATION REPORT")
        print("="*50)
        print(df.to_string(index=False))

        output_path = Path("benchmark/analysis/comprehensive_evaluation.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"\nResults saved to: {output_path}")

if __name__ == "__main__":
    evaluator = Evaluator()
    evaluator.run_all(Path("data"), Path("benchmark"))
