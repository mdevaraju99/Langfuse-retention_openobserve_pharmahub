import os
import logging
from neo4j import GraphDatabase
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
import hashlib
import re

import config

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Neo4jManager:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password")
        self.driver = None
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.verify_connectivity()
        except Exception as e:
            logger.error(f"Failed to create Neo4j driver: {e}")

    def close(self):
        if self.driver:
            self.driver.close()

    def verify_connectivity(self):
        try:
            self.driver.verify_connectivity()
            logger.info("Connected to Neo4j successfully.")
        except Exception as e:
            logger.error(f"Could not connect to Neo4j: {e}")
            raise

    def create_vector_index(self):
        """Creates a vector index on Chunk nodes if it doesn't exist."""
        index_name = getattr(config, "NEO4J_VECTOR_INDEX_NAME", "chunk_embeddings")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", index_name or ""):
            logger.warning("Invalid NEO4J_VECTOR_INDEX_NAME; falling back to 'chunk_embeddings'.")
            index_name = "chunk_embeddings"
        check_query = (
            "SHOW INDEXES YIELD name WHERE name = $index_name RETURN count(*) as count"
        )

        create_query = f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR (c:Chunk) ON (c.embedding)
        OPTIONS {{indexConfig: {{
         `vector.dimensions`: 384,
         `vector.similarity_function`: 'cosine'
        }}}}
        """
        try:
            with self.driver.session() as session:
                result = session.run(check_query, index_name=index_name)
                count = result.single()["count"]
                if count > 0:
                    logger.info("Vector index '%s' already exists. Skipping creation.", index_name)
                    return

                logger.info("Creating vector index '%s'...", index_name)
                session.run(create_query)
                logger.info("Vector index creation command sent.")
        except Exception as e:
            logger.error(f"Error checking/creating vector index: {e}")

    def _compute_file_hash(self, filename: str, content_preview: str = "") -> str:
        """Compute a hash for deduplication"""
        hash_input = f"{filename}_{content_preview[:500]}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    def add_document(
        self,
        filename: str,
        chunks: List[str],
        embeddings: List[List[float]],
        doc_type: str = "unknown",
        entities_per_chunk: Optional[List[Dict]] = None,
        media_metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Adds a document and its chunks to the graph with entity extraction.
        
        Args:
            filename (str): Name of the file.
            chunks (list of str): Text content of chunks.
            embeddings (list of list of floats): Embeddings for each chunk.
            doc_type (str): Type of document (clinical_trial, research_paper, etc.)
            entities_per_chunk (list of dict): Entities extracted for each chunk
        """
        file_hash = self._compute_file_hash(filename, chunks[0] if chunks else "")
        
        # Check if document already exists
        check_query = "MATCH (d:Document {file_hash: $hash}) RETURN count(d) as count"
        try:
            with self.driver.session() as session:
                result = session.run(check_query, hash=file_hash)
                if result.single()["count"] > 0:
                    logger.warning(f"Document '{filename}' already exists (same hash). Skipping.")
                    return
        except Exception as e:
            logger.error(f"Error checking for duplicate: {e}")
        
        # Create document and chunks
        query = """
        CREATE (d:Document {
            filename: $filename,
            upload_date: datetime(),
            doc_type: $doc_type,
            file_hash: $file_hash,
            chunk_count: size($chunks),
            table_count: $table_count,
            image_count: $image_count,
            formula_like_count: $formula_like_count,
            chart_like_count: $chart_like_count
        })
        WITH d
        UNWIND range(0, size($chunks)-1) AS i
        CREATE (c:Chunk {
            text: $chunks[i],
            embedding: $embeddings[i],
            chunk_index: i
        })
        MERGE (d)-[:HAS_CHUNK]->(c)
        WITH c, i, d
        ORDER BY i
        WITH d, collect(c) as chunk_nodes
        FOREACH (j in range(0, size(chunk_nodes)-2) |
            FOREACH (c1 in [chunk_nodes[j]] |
                FOREACH (c2 in [chunk_nodes[j+1]] |
                    MERGE (c1)-[:NEXT]->(c2)
                )
            )
        )
        RETURN d, chunk_nodes
        """
        try:
            with self.driver.session() as session:
                meta = media_metadata or {}
                result = session.run(
                    query,
                    filename=filename,
                    chunks=chunks,
                    embeddings=embeddings,
                    doc_type=doc_type,
                    file_hash=file_hash,
                    table_count=int(meta.get("table_count", 0)),
                    image_count=int(meta.get("image_count", 0)),
                    formula_like_count=int(meta.get("formula_like_count", 0)),
                    chart_like_count=int(meta.get("chart_like_count", 0)),
                )
                result.consume()
                
                # Add entities if provided
                if entities_per_chunk:
                    self._add_entities_to_chunks(filename, chunks, entities_per_chunk)
                
            logger.info(f"Document '{filename}' added with {len(chunks)} chunks.")
        except Exception as e:
            logger.error(f"Error adding document: {e}")
            raise

    def _add_entities_to_chunks(self, filename: str, chunks: List[str], entities_per_chunk: List[Dict]):
        """Add entity nodes and MENTIONS relationships"""
        try:
            with self.driver.session() as session:
                for chunk_idx, entities_dict in enumerate(entities_per_chunk):
                    for entity_type, entity_list in entities_dict.items():
                        for entity_name in entity_list:
                            # Create/merge entity and link to chunk
                            query = """
                            MATCH (d:Document {filename: $filename})-[:HAS_CHUNK]->(c:Chunk {chunk_index: $chunk_idx})
                            MERGE (e:Entity {name: $entity_name, type: $entity_type})
                            ON CREATE SET e.mentions_count = 1
                            ON MATCH SET e.mentions_count = e.mentions_count + 1
                            MERGE (c)-[:MENTIONS]->(e)
                            """
                            session.run(query, filename=filename, chunk_idx=chunk_idx, 
                                      entity_name=entity_name, entity_type=entity_type)
            logger.info(f"Added entities for document '{filename}'")
        except Exception as e:
            logger.error(f"Error adding entities: {e}")

    def create_cross_document_links(self, similarity_threshold: float = 0.75):
        """
        Create SIMILAR_TO relationships between chunks from different documents.
        Uses cosine similarity of embeddings.
        """
        query = """
        MATCH (c1:Chunk)<-[:HAS_CHUNK]-(d1:Document)
        MATCH (c2:Chunk)<-[:HAS_CHUNK]-(d2:Document)
        WHERE d1.filename < d2.filename  // Avoid duplicates and self-links
        AND c1.embedding IS NOT NULL AND c2.embedding IS NOT NULL
        WITH c1, c2, 
             gds.similarity.cosine(c1.embedding, c2.embedding) AS similarity
        WHERE similarity >= $threshold
        MERGE (c1)-[s:SIMILAR_TO]->(c2)
        SET s.score = similarity
        RETURN count(s) as relationships_created
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, threshold=similarity_threshold)
                count = result.single()["relationships_created"]
                logger.info(f"Created {count} cross-document SIMILAR_TO relationships")
                return count
        except Exception as e:
            logger.error(f"Error creating cross-document links: {e}")
            # Fallback: use manual cosine similarity calculation
            return self._create_cross_doc_links_manual(similarity_threshold)

    def _create_cross_doc_links_manual(self, similarity_threshold: float = 0.75):
        """Fallback method using Python-based similarity computation"""
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        
        try:
            with self.driver.session() as session:
                # Get all chunks with embeddings grouped by document
                query = """
                MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
                WHERE c.embedding IS NOT NULL
                RETURN id(c) as chunk_id, c.embedding as embedding, d.filename as doc
                """
                result = session.run(query)
                chunks_data = [(record["chunk_id"], np.array(record["embedding"]), record["doc"]) 
                              for record in result]
                
                if len(chunks_data) < 2:
                    logger.warning("Not enough chunks for cross-document linking")
                    return 0
                
                # Group by document
                doc_chunks = {}
                for chunk_id, embedding, doc in chunks_data:
                    if doc not in doc_chunks:
                        doc_chunks[doc] = []
                    doc_chunks[doc].append((chunk_id, embedding))
                
                # Compare chunks across different documents
                relationship_count = 0
                doc_names = list(doc_chunks.keys())
                
                for i in range(len(doc_names)):
                    for j in range(i + 1, len(doc_names)):
                        doc1_chunks = doc_chunks[doc_names[i]]
                        doc2_chunks = doc_chunks[doc_names[j]]
                        
                        # Compute similarities
                        for chunk1_id, emb1 in doc1_chunks:
                            for chunk2_id, emb2 in doc2_chunks:
                                similarity = cosine_similarity([emb1], [emb2])[0][0]
                                
                                if similarity >= similarity_threshold:
                                    # Create relationship
                                    create_rel_query = """
                                    MATCH (c1:Chunk), (c2:Chunk)
                                    WHERE id(c1) = $id1 AND id(c2) = $id2
                                    MERGE (c1)-[s:SIMILAR_TO]->(c2)
                                    SET s.score = $score
                                    """
                                    session.run(create_rel_query, id1=chunk1_id, id2=chunk2_id, score=float(similarity))
                                    relationship_count += 1
                
                logger.info(f"Created {relationship_count} cross-document relationships (manual method)")
                return relationship_count
        except Exception as e:
            logger.error(f"Error in manual cross-document linking: {e}")
            return 0

    def get_documents(self) -> List[Dict[str, Any]]:
        """Get list of all documents in the graph"""
        query = """
        MATCH (d:Document)
        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
        RETURN d.filename as filename, d.upload_date as upload_date, 
               d.doc_type as doc_type, count(c) as chunk_count,
               d.table_count as table_count, d.image_count as image_count,
               d.formula_like_count as formula_like_count,
               d.chart_like_count as chart_like_count
        ORDER BY d.upload_date DESC
        """
        try:
            with self.driver.session() as session:
                result = session.run(query)
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error fetching documents: {e}")
            return []

    def delete_document(self, filename: str):
        """Delete a document and all its related nodes"""
        query = """
        MATCH (d:Document {filename: $filename})
        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
        OPTIONAL MATCH (c)-[r]-()
        DELETE r, c, d
        """
        try:
            with self.driver.session() as session:
                session.run(query, filename=filename)
                logger.info(f"Deleted document '{filename}' and its chunks")
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            raise

    def query_similar_chunks(self, query_embedding, top_k=5):
        """
        Finds similar chunks using vector search.
        """
        index_name = getattr(config, "NEO4J_VECTOR_INDEX_NAME", "chunk_embeddings")
        query = f"""
        CALL db.index.vector.queryNodes('{index_name}', $top_k, $query_embedding)
        YIELD node, score
        MATCH (node)<-[:HAS_CHUNK]-(d:Document)
        RETURN node.text AS text, score, node.chunk_index AS index, 
               d.filename AS document, d.doc_type AS doc_type
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, query_embedding=query_embedding, top_k=top_k)
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Error querying similar chunks: {e}")
            return []

    def get_context(self, query_embedding, window=1, top_k=10):
        """
        Retrieves similar chunks and their neighbors (window) for better context.
        Enhanced for multi-document retrieval.
        """
        # First get top matches
        similar_chunks = self.query_similar_chunks(query_embedding, top_k=top_k)
        
        context_parts = []
        seen_texts = set()  # Deduplication
        
        for chunk in similar_chunks:
            chunk_text = chunk['text']
            if chunk_text not in seen_texts:
                doc_name = chunk.get('document', 'Unknown')
                context_parts.append(f"[Source: {doc_name}]\n{chunk_text}")
                seen_texts.add(chunk_text)
            
        return "\n\n---\n\n".join(context_parts)
    
    def get_multi_doc_context(
        self,
        query_embedding,
        top_k=15,
        max_docs=5,
        traverse_graph=True,
        user_query: Optional[str] = None,
    ):
        """
        Enhanced retrieval for multi-document questions.
        Uses a hybrid approach: vector search + keyword fallback + context expansion.
        
        Args:
            query_embedding: Query vector
            top_k: Number of initial chunks to retrieve
            max_docs: Maximum number of documents to pull from
            traverse_graph: Whether to follow SIMILAR_TO and NEXT relationships
        """
        # Step 1: Try vector search
        similar_chunks = self.query_similar_chunks(query_embedding, top_k=top_k)
        
        # Step 2: If vector search fails or returns too few results, use fallback
        if not similar_chunks or len(similar_chunks) < 3:
            logger.info("Vector search returned insufficient results, using hybrid retrieval")
            return self._get_context_hybrid(top_k=top_k, max_docs=max_docs, user_query=user_query)
        
        # Step 3: Get document diversity (limit to max_docs)
        docs_seen = set()
        selected_chunks = []
        
        for chunk in similar_chunks:
            doc = chunk.get('document', '')
            if doc and (len(docs_seen) < max_docs or doc in docs_seen):
                selected_chunks.append(chunk)
                docs_seen.add(doc)
        
        # Step 4: Expand context with neighboring chunks
        context_parts = []
        seen_texts = set()
        chunk_indices = {}  # Track chunk indices for context expansion
        
        for chunk in selected_chunks[:top_k]:
            chunk_text = chunk['text']
            doc_name = chunk.get('document', 'Unknown')
            chunk_idx = chunk.get('index', 0)
            
            if chunk_text not in seen_texts:
                context_parts.append(f"[Source: {doc_name}]\n{chunk_text}")
                seen_texts.add(chunk_text)
                chunk_indices[chunk_idx] = doc_name
        
        # Step 5: Optionally expand with NEXT chunks
        if traverse_graph and chunk_indices:
            try:
                with self.driver.session() as session:
                    for chunk_idx, doc_name in list(chunk_indices.items())[:3]:
                        next_query = """
                        MATCH (d:Document {filename: $doc})-[:HAS_CHUNK]->(c1:Chunk {chunk_index: $idx})
                        OPTIONAL MATCH (c1)-[:NEXT]->(c2:Chunk)
                        RETURN c2.text as next_text
                        LIMIT 2
                        """
                        result = session.run(next_query, doc=doc_name, idx=chunk_idx)
                        for record in result:
                            next_text = record.get('next_text')
                            if next_text and next_text not in seen_texts:
                                context_parts.append(f"[Continuation from {doc_name}]\n{next_text}")
                                seen_texts.add(next_text)
            except Exception as e:
                logger.warning(f"Context expansion failed: {e}. Continuing with base results.")
        
        return "\n\n---\n\n".join(context_parts)
    
    @staticmethod
    def _cypher_escape_literal(s: str) -> str:
        """Escape for safe use inside single-quoted Cypher string literals."""
        return (s or "").replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def _keywords_from_query(user_query: Optional[str], max_terms: int = 10) -> List[str]:
        if not user_query:
            return []
        stop = {
            "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are",
            "was", "were", "be", "been", "being", "what", "how", "why", "when", "where", "which",
            "does", "do", "did", "can", "could", "would", "should", "may", "might", "this", "that",
            "these", "those", "from", "into", "about", "than", "then", "it", "its", "as", "at", "by",
        }
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\%]{2,}", user_query.lower())
        out: List[str] = []
        for t in tokens:
            if t in stop:
                continue
            if t not in out:
                out.append(t)
            if len(out) >= max_terms:
                break
        return out

    def _get_context_hybrid(self, top_k=15, max_docs=5, user_query: Optional[str] = None) -> str:
        """
        Fallback hybrid retrieval: keyword matching + semantic matching
        when vector search is unavailable or insufficient.
        """
        context_parts = []
        seen_texts = set()
        
        # Config-driven fallback keywords (kept customizable in config/.env)
        clinical_keywords = list(getattr(config, "RAG_HYBRID_FALLBACK_KEYWORDS", []) or [])

        query_terms = self._keywords_from_query(user_query, max_terms=12)
        # Prefer longer / more specific tokens first
        query_terms.sort(key=len, reverse=True)
        combined_keywords: List[str] = []
        for kw in clinical_keywords + query_terms:
            if kw not in combined_keywords:
                combined_keywords.append(kw)
        combined_keywords = combined_keywords[:24]
        
        try:
            with self.driver.session() as session:
                # Build WHERE clause for keywords
                keyword_or = " OR ".join(
                    [f"c.text CONTAINS '{self._cypher_escape_literal(kw)}'" for kw in combined_keywords]
                )
                if not keyword_or.strip():
                    return ""

                query = f"""
                MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
                WHERE {keyword_or}
                RETURN c.text as text, c.chunk_index as idx, d.filename as doc,
                       count(*) as match_count
                ORDER BY match_count DESC, c.chunk_index ASC
                LIMIT {int(top_k)}
                """
                
                result = session.run(query)
                
                for record in result:
                    chunk_text = record['text']
                    doc_name = record['doc']
                    
                    if chunk_text not in seen_texts:
                        context_parts.append(f"[Source: {doc_name}]\n{chunk_text}")
                        seen_texts.add(chunk_text)
        except Exception as e:
            logger.error(f"Hybrid retrieval failed: {e}")
        
        return "\n\n---\n\n".join(context_parts)

    def query_by_entity(self, entity_name: str, top_k: int = 5) -> List[Dict]:
        """Find chunks that mention a specific entity"""
        query = """
        MATCH (e:Entity {name: $entity_name})<-[:MENTIONS]-(c:Chunk)<-[:HAS_CHUNK]-(d:Document)
        RETURN c.text as text, d.filename as document, c.chunk_index as index
        LIMIT $top_k
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, entity_name=entity_name, top_k=top_k)
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Error querying by entity: {e}")
            return []
    
    def clear_all_data(self):
        """Clear all documents, chunks, and entities from the database"""
        query = "MATCH (n) DETACH DELETE n"
        try:
            with self.driver.session() as session:
                session.run(query)
                logger.info("Cleared all data from Neo4j")
        except Exception as e:
            logger.error(f"Error clearing data: {e}")
            raise
