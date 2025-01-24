from typing import Dict, List, Optional, Union
from datetime import datetime
from .store import VectorStore
from .types import Memory, SearchResult
from pypdf import PdfReader
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self, agent_name: str):
        self.store = VectorStore(agent_name)

    def create(self, 
               category: str, 
               content: str, 
               metadata: Optional[Dict] = None) -> Memory:
        """Create a new memory"""
        metadata = metadata or {}
        metadata.update({
            "timestamp": datetime.now().isoformat(),
        })
        
        return self.store.add(category, content, metadata)

    def search(
        self, 
        query: str,
        category: Optional[Union[str, List[str]]] = None,
        n_results: int = 5,
        min_similarity: float = 0.2,
        filter_metadata: Optional[Dict] = None
    ) -> List[SearchResult]:
        """Search for similar memories across one or multiple categories"""
        available_categories = self.list_categories()
        if not available_categories:
            return []
        
        # Determine categories to search
        if category is None:
            categories = available_categories
        elif isinstance(category, str):
            categories = [category] if category in available_categories else []
        else:  # List of categories
            categories = [cat for cat in category if cat in available_categories]
        
        # Search each category
        results = []
        for cat in categories:
            if cat in self.store.collections:
                cat_results = self.store.search(
                    cat,
                    query,
                    n_results=n_results,
                    filter_metadata=filter_metadata
                )
                results.extend(cat_results)
        
        # Sort and filter results
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        filtered_results = [
            result for result in results 
            if result.similarity_score > min_similarity
        ]
        
        return filtered_results[:n_results]

    def get_memories(
        self,
        category: str,
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None
    ) -> List[Memory]:
        """Get most recent memories from a category"""
        try:
            return self.store.get_memories(category, n_results, filter_metadata)
        except Exception as e:
            logger.error(f"Error getting recent memories from {category}: {e}")
            return []
        
    def get_relevant_context(self, query: str, n_results: int = 3) -> tuple[str, List[SearchResult]]:
        """Get relevant memory context for a query"""
        if len(query.split()) <= 3: # Basic complexity check
            return "", []

        results = self.search(query=query, n_results=n_results) 
        if not results:
            return "", []

        context = "\n\n".join(
            f"From {result.memory.metadata.get('source', 'reference')}:\n{result.memory.content}"
            for result in results
        )

        return context, results

    def list_categories(self) -> List[str]:
        """List all memory categories"""
        return self.store.list_categories()

    def split_document(self, text: str, 
                        chunk_size: int = 500, 
                        chunk_overlap: int = 100,
                        respect_boundaries: bool = True) -> List[Dict[str, Optional[str]]]:
        """
        Split a document into overlapping chunks while attempting to respect content boundaries.
        
        Args:
            text: Source text to split
            chunk_size: Target size for each chunk in characters
            chunk_overlap: Number of characters to overlap between chunks
            respect_boundaries: Try to break at sentence/paragraph boundaries when possible
        """
        sections = []
        
        # First, split into coarse sections based on headers
        coarse_sections = []
        current_section = []
        current_header = None
        
        for line in text.splitlines():
            stripped = line.strip()
            
            # Detect headers
            if stripped.startswith('# ') or (stripped.isupper() and len(stripped) > 4):
                if current_section:
                    coarse_sections.append({
                        'header': current_header,
                        'content': '\n'.join(current_section)
                    })
                current_header = stripped.lstrip('#').strip()
                current_section = []
            current_section.append(line)
        
        # Add final section
        if current_section:
            coarse_sections.append({
                'header': current_header,
                'content': '\n'.join(current_section)
            })
        
        # Now split each coarse section into smaller chunks
        for section in coarse_sections:
            content = section['content']
            header = section['header']
            
            # If content is short enough, keep it as one chunk
            if len(content) <= chunk_size:
                sections.append({
                    'header': header,
                    'content': content.strip()
                })
                continue
            
            # Split into overlapping chunks
            start = 0
            while start < len(content):
                # Find end of chunk
                end = start + chunk_size
                
                if respect_boundaries and end < len(content):
                    # Try to find sentence boundary
                    sentence_end = content.find('. ', end - 50, end + 50)
                    if sentence_end != -1:
                        end = sentence_end + 1
                    else:
                        # Try paragraph boundary
                        para_end = content.find('\n\n', end - 50, end + 50)
                        if para_end != -1:
                            end = para_end
                
                chunk_content = content[start:end].strip()
                if chunk_content:  # Only add non-empty chunks
                    sections.append({
                        'header': header,
                        'content': chunk_content
                    })
                
                # Move start for next chunk, considering overlap
                start = end - chunk_overlap
                if start < 0:
                    start = 0
        
        return sections

    def create_chunks(self,
                    file_path: str,
                    category: str,
                    metadata: Optional[Dict] = None) -> List[str]:
        memory_ids = []
        file_extension = Path(file_path).suffix[1:].lower()
        base_metadata = {
            "source": file_path,
            "document_type": file_extension,
            **(metadata or {})
        }
        
        try:
            # PDF handling
            if file_extension == 'pdf':
                reader = PdfReader(file_path)
                text = ""
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    if page_text.strip():
                        text += f"Page {i+1} of {len(reader.pages)}:\n{page_text}\n\n"
                
                base_metadata.update({
                    "total_pages": len(reader.pages),
                    "has_text": bool(text.strip())
                })
            else:
                # Default to text reading for all other files
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
            
            # Use existing split_document method
            sections = self.split_document(text)
            
            # Create memories for each section
            for i, section in enumerate(sections):
                section_metadata = {
                    **base_metadata,
                    "chunk_index": i,
                    "chunks_total": len(sections),
                    "section_header": section['header'],
                    "chunk_size": len(section['content']),
                    "has_code": bool(re.search(r'```.*```', section['content'], re.DOTALL))
                }
                
                memory = self.create(
                    category=category,
                    content=section['content'],
                    metadata=section_metadata
                )
                memory_ids.append(memory.id)
            
            return memory_ids
            
        except Exception as e:
            logger.error(f"Failed to process document {file_path}: {str(e)}")
            raise

    def upload_documents(self, filepaths: List[str], category: str, metadata: Optional[Dict] = None) -> Dict[str, int]:
        """Upload multiple documents to memory, returning statistics about the operation."""
        successful = 0
        failed = 0
        total_chunks = 0
        
        for filepath in filepaths:
            try:
                memory_ids = self.create_chunks(
                    filepath,
                    category=category,
                    metadata={
                        "type": "document",
                        "original_filename": filepath,
                        "upload_timestamp": datetime.now().isoformat(),
                        **(metadata or {})
                    }
                )
                successful += 1
                total_chunks += len(memory_ids)
            except FileNotFoundError:
                failed += 1
            except Exception as e:
                logger.error(f"Error processing {filepath}: {e}")
                failed += 1
        
        return {
            "total_attempted": len(filepaths),
            "successful": successful,
            "failed": failed,
            "total_chunks": total_chunks
        }
    
    def get_category_stats(self, category: str) -> Dict[str, Union[int, List[Dict]]]:
        """Get detailed statistics about a category's contents."""
        if category not in self.store.collections:
            return {
                "document_count": 0,
                "total_chunks": 0,
                "documents": []
            }
        
        memories = self.get_memories(category, n_results=1000)

        # Handle empty category
        if not memories:
            return {
                "document_count": 0,
                "total_chunks": 0,
                "documents": []
            }
        
        # Group memories by original filename
        from collections import defaultdict
        docs = defaultdict(list)
        for memory in memories:
            filename = memory.metadata.get('original_filename', 'Unknown source')
            docs[filename].append(memory)
        
        documents = []
        for filename, chunks in docs.items():
            documents.append({
                "filename": filename,
                "chunk_count": len(chunks),
                "total_size": sum(len(chunk.content) for chunk in chunks),
                "upload_date": chunks[0].metadata.get('upload_timestamp', 'Unknown')[:10]
            })
        
        return {
            "document_count": len(docs),
            "total_chunks": len(memories),
            "documents": documents
        }
    
    def delete_memory(self, category: str, memory_id: str) -> bool:
        """Delete a specific memory"""
        return self.store.delete(category, memory_id)
    
    def remove_category(self, category: str) -> bool:
        """Delete an entire category of memories"""
        try:
            if category in self.store.collections:
                # Get the collection
                collection = self.store.collections[category]
                
                # Delete the collection from ChromaDB
                self.store.client.delete_collection(category)
                
                # Remove from our collections dict
                del self.store.collections[category]
                
                return True
        except Exception as e:
            logger.error(f"Error deleting category {category}: {e}")
            return False
        
    def wipe_document(self, category: str, filename: str) -> int:
        """Delete all chunks belonging to a specific document."""
        memories = self.get_memories(category, n_results=1000)
        chunks_deleted = 0
        
        for memory in memories:
            if memory.metadata.get('original_filename') == filename:
                if self.delete_memory(category, memory.id):
                    chunks_deleted += 1
        
        return chunks_deleted

    def wipe_category(self, category: str) -> Dict[str, int]:
        """Delete all memories in a category."""
        stats = self.get_category_stats(category)
        success = self.remove_category(category)
        return {
            "success": success,
            "documents_deleted": stats["document_count"],
            "chunks_deleted": stats["total_chunks"]
        }
    
    def wipe_all_memories(self) -> bool:
        """Delete all memories and collections."""
        try:
            for category in self.list_categories():
                self.remove_category(category)
            return True
        except Exception as e:
            logger.error(f"Error wiping all memories: {e}")
            return False