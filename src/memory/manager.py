from typing import Dict, List, Optional, Union
from datetime import datetime
from .store import VectorStore
from .types import Memory, SearchResult, EpochInfo
from pypdf import PdfReader
from pathlib import Path
from io import BytesIO
import logging
import re

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self, agent_name: str):
        self.store = VectorStore(agent_name)
        self.current_epoch = EpochInfo(
            epoch_number=1,
            start_time=datetime.now()
        )

    def create(self, 
               category: str, 
               content: str, 
               metadata: Optional[Dict] = None) -> Memory:
        """Create a new memory"""
        metadata = metadata or {}
        metadata.update({
            "timestamp": datetime.now().isoformat(),
            "epoch": self.current_epoch.epoch_number
        })
        
        return self.store.add(category, content, metadata)

    def search(
        self, 
        category: Union[str, List[str]],  # Keep this to allow both single category and list
        query: str,
        n_results: int = 3,
        min_similarity: float = 0.1,
        filter_metadata: Optional[Dict] = None
    ) -> List[SearchResult]:
        """Search for similar memories across one or multiple categories"""
        results = []
        
        # Convert single category to list for uniform handling
        categories = [category] if isinstance(category, str) else category
        
        # Search each category
        for cat in categories:
            if cat in self.store.collections:
                cat_results = self.store.search(
                    cat,
                    query,
                    n_results=n_results,
                    filter_metadata=filter_metadata
                )
                results.extend(cat_results)
        
        # Sort all results by similarity score
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        
        # Filter and limit results
        filtered_results = [
            result for result in results 
            if result.similarity_score > min_similarity
        ]
        
        return filtered_results[:n_results]

    def get_by_id(self, category: str, memory_id: str) -> Optional[Memory]:
        """Retrieve a specific memory by ID"""
        return self.store.get(category, memory_id)

    def get_recent(
        self,
        category: str,
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None
    ) -> List[Memory]:
        """Get most recent memories from a category"""
        try:
            return self.store.get_recent(category, n_results, filter_metadata)
        except Exception as e:
            logger.error(f"Error getting recent memories from {category}: {e}")
            return []

    def increment_epoch(self, metadata: Optional[Dict] = None) -> EpochInfo:
        """Start a new epoch"""
        self.current_epoch = EpochInfo(
            epoch_number=self.current_epoch.epoch_number + 1,
            start_time=datetime.now(),
            metadata=metadata
        )
        return self.current_epoch

    def get_current_epoch(self) -> EpochInfo:
        """Get current epoch information"""
        return self.current_epoch
    

    def list_categories(self) -> List[str]:
        """List all memory categories"""
        return self.store.list_categories()

    def count(self, category: str) -> int:
        """Count memories in a category"""
        if category not in self.store.collections:
            return 0
        
        collection = self.store.collections[category]
        return len(collection.get()['ids'])

    def get_or_create_collection(self, category: str):
        """Get an existing collection or create it if it doesn't exist"""
        return self.store.get_or_create_collection(category)

    def delete(self, category: str, memory_id: str) -> bool:
        """Delete a specific memory"""
        return self.store.delete(category, memory_id)

    def update(self, category: str, memory_id: str, content: Optional[str] = None, metadata: Optional[Dict] = None) -> bool:
        """Update a memory's content and/or metadata"""
        if category not in self.store.collections:
            return False
        
        try:
            collection = self.store.collections[category]
            
            # If we're updating content, we need to re-embed it
            if content:
                collection.update(
                    ids=[memory_id],
                    documents=[content],
                    metadatas=[metadata] if metadata else None
                )
            # If we're only updating metadata, no need to re-embed
            elif metadata:
                collection.update(
                    ids=[memory_id],
                    metadatas=[metadata]
                )
            
            return True
        except Exception:
            return False

    def split_document(self, text: str, 
                        chunk_size: int = 500, 
                        chunk_overlap: int = 100,
                        respect_boundaries: bool = True) -> List[Dict[str, str]]:
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
        """
        Create memory chunks from any document type while preserving structure
        """
        memory_ids = []
        base_metadata = {
            "source": file_path,
            "document_type": Path(file_path).suffix[1:],  # Remove dot from extension
            **(metadata or {})
        }
        
        try:
            # Read the file
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
            
            # Split into logical sections
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
    
    def delete_category(self, category: str) -> bool:
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