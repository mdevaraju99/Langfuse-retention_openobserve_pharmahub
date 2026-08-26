from contextlib import nullcontext
import time
from langchain_text_splitters import RecursiveCharacterTextSplitter
import streamlit as st
import re
from typing import Dict, List, Tuple, Optional

import config
from .neo4j_manager import Neo4jManager
from .entity_extractor import get_entity_extractor
from .pdf_extract import (
    extract_pdf_text_and_tables,
    extract_pdf_media_assets,
    load_media_manifest,
    delete_media_assets,
    clear_media_assets,
)

# Initialize model once (lazy import: avoid pulling TF/keras; see app.py USE_TF=0)
@st.cache_resource
def get_embedding_model():
    import os

    # Keep sentence-transformers on the PyTorch path only.
    # In some Windows Python setups, transformers may try optional TF/Keras
    # integrations and fail even though we don't use them.
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("USE_FLAX", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("DISABLE_TELEMETRY", "1")
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")

def process_pdf_with_metadata(file) -> Tuple[str, Dict[str, int]]:
    """
    Extracts text (and best-effort tables) from a PDF using PyMuPDF with pypdf fallback.
    """
    try:
        file.seek(0)
        text, _pages, _engine, media_metadata = extract_pdf_text_and_tables(
            file,
            max_pages=config.RAG_MAX_PDF_PAGES,
            max_chars=config.RAG_MAX_INGEST_CHARS,
        )
        return (
            text or "",
            media_metadata
            or {
                "table_count": 0,
                "image_count": 0,
                "formula_like_count": 0,
                "chart_like_count": 0,
            },
        )
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return "", {
            "table_count": 0,
            "image_count": 0,
            "formula_like_count": 0,
            "chart_like_count": 0,
        }


def process_pdf(file) -> str:
    """
    Backward-compatible text-only API used by legacy debug scripts.
    """
    text, _meta = process_pdf_with_metadata(file)
    return text


def check_neo4j_connection() -> Tuple[bool, str]:
    """
    Preflight Neo4j connection for ingestion/query operations.
    Returns (ok, message) with actionable guidance on failure.
    """
    neo: Optional[Neo4jManager] = None
    try:
        neo = Neo4jManager()
        if not neo.driver:
            return (
                False,
                "Neo4j driver could not be created. Check NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD.",
            )
        neo.verify_connectivity()
        return True, "Neo4j connection successful."
    except Exception as e:
        return (
            False,
            "Neo4j is not reachable. Start Neo4j and verify credentials in `.env` "
            f"(NEO4J_URI={config.NEO4J_URI}, NEO4J_USER={config.NEO4J_USER}). "
            f"Details: {e}",
        )
    finally:
        if neo:
            neo.close()

def chunk_text(text, chunk_size=1000, chunk_overlap=200):
    """
    Splits text into chunks.
    """
    if not text:
        return []
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len
    )
    return splitter.split_text(text)

def generate_embeddings(chunks):
    """
    Generates embeddings for a list of text chunks.
    """
    try:
        model = get_embedding_model()
        return model.encode(chunks).tolist()
    except Exception as e:
        print(f"Embedding Error: {e}")
        return []

def detect_document_type(text: str) -> str:
    """
    Detect document type from content using keywords.
    """
    text_lower = text.lower()
    
    # Keywords for different document types
    if any(keyword in text_lower for keyword in ['clinical trial', 'protocol', 'nct', 'phase 1', 'phase 2', 'phase 3', 'study design']):
        if 'results' in text_lower or 'outcome' in text_lower:
            return 'clinical_trial_results'
        return 'clinical_trial_protocol'
    
    if any(keyword in text_lower for keyword in ['mechanism of action', 'pharmacology', 'pharmacokinetics', 'drug mechanism']):
        return 'drug_mechanism'
    
    if any(keyword in text_lower for keyword in ['abstract', 'introduction', 'methods', 'discussion', 'references']):
        return 'research_paper'
    
    if any(keyword in text_lower for keyword in ['indication', 'dosage', 'administration', 'contraindication', 'warnings']):
        return 'drug_label'
    
    return 'unknown'

def ingest_document(file, filename: str) -> Tuple[bool, str]:
    """
    Full pipeline: Parse -> Chunk -> Embed -> Extract Entities -> Neo4j
    """
    try:
        ok, conn_msg = check_neo4j_connection()
        if not ok:
            return False, f"Ingestion Error: {conn_msg}"

        file.seek(0, 2)
        size_bytes = file.tell()
        file.seek(0)
        max_bytes = int(config.RAG_MAX_PDF_MB) * 1024 * 1024
        if size_bytes > max_bytes:
            return False, (
                f"File too large ({size_bytes // (1024 * 1024)} MB). "
                f"Configured limit is {config.RAG_MAX_PDF_MB} MB (see RAG_MAX_PDF_MB)."
            )

        # 1. Parse
        text, media_metadata = process_pdf_with_metadata(file)
        if not text:
            return False, "Could not extract text from PDF. The file might be empty or scanned (image-only)."
        media_manifest = extract_pdf_media_assets(
            file,
            filename=filename,
            max_pages=config.RAG_MAX_PDF_PAGES,
            output_dir=config.MEDIA_ASSETS_DIR,
            max_images=config.RAG_MAX_MEDIA_IMAGES,
            max_tables=config.RAG_MAX_MEDIA_TABLE_PREVIEWS,
            max_snippets=config.RAG_MAX_MEDIA_SNIPPETS,
        )
            
        # 2. Detect document type
        doc_type = detect_document_type(text)
        
        # 3. Chunk
        chunks = chunk_text(text)
        if not chunks:
            return False, "Text extraction returned empty content after processing."

        max_chunks = int(config.RAG_MAX_CHUNKS_PER_DOC)
        truncated_note = ""
        if len(chunks) > max_chunks:
            chunks = chunks[:max_chunks]
            truncated_note = f" (truncated to {max_chunks} chunks for scalability; adjust RAG_MAX_CHUNKS_PER_DOC if needed)"
        
        # 4. Embed
        embeddings = generate_embeddings(chunks)
        
        # 5. Extract entities
        extractor = get_entity_extractor()
        entities_per_chunk = extractor.extract_entities_batch(chunks)
        
        # 6. Neo4j
        neo = Neo4jManager()
        neo.create_vector_index()  # Ensure index exists
        neo.add_document(
            filename,
            chunks,
            embeddings,
            doc_type,
            entities_per_chunk,
            media_metadata=media_metadata,
        )
        neo.close()
        
        # Count entities
        total_entities = sum(len(extractor.get_entity_set(e)) for e in entities_per_chunk)
        
        return True, (
            f"Successfully processed {filename} ({doc_type}). Created {len(chunks)} chunks with "
            f"{total_entities} unique entities."
            f" Tables: {int(media_metadata.get('table_count', 0))},"
            f" Images: {int(media_metadata.get('image_count', 0))},"
            f" Formula-like blocks: {int(media_metadata.get('formula_like_count', 0))}."
            f" Chart-like mentions: {int(media_metadata.get('chart_like_count', 0))}."
            f" Rich-media previews: tables={len(media_manifest.get('tables', []))},"
            f" images={len(media_manifest.get('images', []))},"
            f" formulas={len(media_manifest.get('formula_snippets', []))},"
            f" charts={len(media_manifest.get('chart_snippets', []))}."
            f"{truncated_note}"
        )
    except Exception as e:
        return False, f"Ingestion Error: {str(e)}"

def ingest_documents_batch(files: List, filenames: List[str]) -> Tuple[bool, str]:
    """
    Process multiple documents and create cross-document relationships.
    
    Args:
        files: List of uploaded file objects
        filenames: List of filenames
        
    Returns:
        Tuple of (success, message)
    """
    if not files or not filenames:
        return False, "No files provided"
    
    if len(files) != len(filenames):
        return False, "File count mismatch"
    
    success_count = 0
    errors = []
    
    # Ingest each document
    for file, filename in zip(files, filenames):
        success, message = ingest_document(file, filename)
        if success:
            success_count += 1
        else:
            errors.append(f"{filename}: {message}")
    
    # Create cross-document relationships if multiple docs uploaded successfully
    if success_count > 1:
        try:
            neo = Neo4jManager()
            rel_count = neo.create_cross_document_links(similarity_threshold=0.75)
            neo.close()
            relationship_msg = f"Created {rel_count} cross-document relationships."
        except Exception as e:
            relationship_msg = f"Warning: Could not create cross-document links: {e}"
    else:
        relationship_msg = ""
    
    # Build result message
    if success_count == len(files):
        return True, f"Successfully processed all {success_count} documents. {relationship_msg}"
    elif success_count > 0:
        error_details = "\n".join(errors)
        return True, f"Processed {success_count}/{len(files)} documents. {relationship_msg}\n\nErrors:\n{error_details}"
    else:
        error_details = "\n".join(errors)
        return False, f"Failed to process all documents:\n{error_details}"

def _get_rag_context_impl(query: str, top_k: int = 15, max_docs: int = 5) -> str:
    """Neo4j retrieval implementation (no Langfuse wrapper)."""
    neo: Optional[Neo4jManager] = None
    try:
        neo = Neo4jManager()
        context = ""

        # Primary path: vector retrieval
        try:
            model = get_embedding_model()
            query_embedding = model.encode([query])[0].tolist()
            context = neo.get_multi_doc_context(
                query_embedding,
                top_k=top_k,
                max_docs=max_docs,
                user_query=query,
            )
        except Exception as embed_err:
            # Keep retrieval alive even if local embedding stack is broken/missing.
            print(f"Embedding path unavailable, switching to hybrid retrieval: {embed_err}")

        # Secondary path: lexical/hybrid fallback (does not require embeddings)
        if not context or len(context.strip()) < 100:
            print(f"Primary retrieval insufficient for query: {query[:50]}...")
            context = neo._get_context_hybrid(top_k=top_k, max_docs=max_docs, user_query=query)

        if context and len(context.strip()) > 0:
            return context
        return ""  # Return empty string to trigger fallback to base knowledge

    except Exception as e:
        print(f"RAG Error: {e}")
        import traceback
        traceback.print_exc()
        return ""
    finally:
        if neo:
            try:
                neo.close()
            except Exception:
                pass


def get_rag_context(query: str, top_k: int = 15, max_docs: int = 5) -> str:
    """
    Retrieves context for a query using multi-document retrieval.
    Enhanced with keyword extraction and fallback strategies.

    When Langfuse is configured, emits a retriever observation (rag.neo4j.retrieve).
    """
    from utils.langfuse_trace import flush_langfuse, get_langfuse_client
    from utils.openobserve_setup import (
        flush_openobserve,
        log_event,
        mark_current_span_error,
        mark_current_span_ok,
        trace_span,
    )

    lf = get_langfuse_client()
    t0 = time.perf_counter()
    cm = (
        lf.start_as_current_observation(
            name="retrieve.neo4j",
            as_type="retriever",
            input={
                "query": (query or "")[:3000],
                "top_k": top_k,
                "max_docs": max_docs,
            },
        )
        if lf
        else nullcontext()
    )
    with trace_span(
        "rag.neo4j.retrieve",
        attributes={
            "rag.top_k": top_k,
            "rag.max_docs": max_docs,
            "rag.query_chars": len(query or ""),
        },
    ):
        with cm as obs:
            result = _get_rag_context_impl(query, top_k=top_k, max_docs=max_docs)
            ms = (time.perf_counter() - t0) * 1000
            from utils.openobserve_metrics import record_rag_retrieval_ms

            record_rag_retrieval_ms(ms, context_chars=len(result or ""))
            log_event(
                "rag.retrieval",
                attributes={
                    "latency_ms": round(ms, 2),
                    "context_chars": len(result or ""),
                    "top_k": top_k,
                },
            )
            if lf and obs is not None:
                try:
                    ms = (time.perf_counter() - t0) * 1000
                    obs.update(
                        output={
                            "context_chars": len(result or ""),
                            "latency_ms": round(ms, 2),
                            "text_preview": (result or "")[:1500],
                        }
                    )
                except Exception:
                    pass
            mark_current_span_ok()
            flush_langfuse()
            flush_openobserve()
            return result

def get_documents_list() -> List[dict]:
    """Get list of all uploaded documents"""
    try:
        neo = Neo4jManager()
        docs = neo.get_documents()
        neo.close()
        return docs
    except Exception as e:
        print(f"Error fetching documents: {e}")
        return []


def get_document_media_assets(filename: str) -> Dict:
    """
    Load persisted rich-media assets for a document (if available).
    """
    try:
        return load_media_manifest(filename, config.MEDIA_ASSETS_DIR) or {}
    except Exception:
        return {}

def delete_document(filename: str) -> Tuple[bool, str]:
    """Delete a specific document"""
    try:
        neo = Neo4jManager()
        neo.delete_document(filename)
        neo.close()
        delete_media_assets(filename, config.MEDIA_ASSETS_DIR)
        return True, f"Successfully deleted {filename}"
    except Exception as e:
        return False, f"Error deleting document: {e}"

def clear_all_documents() -> Tuple[bool, str]:
    """Clear all documents from Neo4j"""
    try:
        neo = Neo4jManager()
        neo.clear_all_data()
        neo.close()
        clear_media_assets(config.MEDIA_ASSETS_DIR)
        return True, "Successfully cleared all documents"
    except Exception as e:
        return False, f"Error clearing documents: {e}"
