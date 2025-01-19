from typing import Dict, List, Optional
from datetime import datetime
from .store import VectorStore
from .types import Memory, SearchResult, EpochInfo
import PyPDF2
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self):
        self.store = VectorStore()
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

    def search(self, 
               category: str,
               query: str,
               n_results: int = 5,
               filter_metadata: Optional[Dict] = None) -> List[SearchResult]:
        """Search for similar memories"""
        return self.store.search(category, query, n_results, filter_metadata)

    def get_by_id(self, category: str, memory_id: str) -> Optional[Memory]:
        """Retrieve a specific memory by ID"""
        return self.store.get(category, memory_id)

    def get_recent(self, 
                   category: str,
                   n_results: int = 10,
                   filter_metadata: Optional[Dict] = None) -> List[Memory]:
        """Get most recent memories"""
        return self.store.get_recent(category, n_results, filter_metadata)

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
        return list(self.store.collections.keys())

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

    def ingest_pdf(self, 
                file_path: str,
                category: str = "reference_materials",
                chunk_size: int = 500,  # Reduced from 1000
                metadata: Optional[Dict] = None) -> List[str]:
        """
        Ingest a PDF document into memory by breaking it into chunks
        """
        memory_ids = []
        base_metadata = {
            "source": file_path,
            "document_type": "pdf",
            **(metadata or {})
        }

        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                
                # Process each page separately
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    
                    # Break page into chunks
                    chunks = self._smart_chunk_text(text, chunk_size)
                    
                    # Store each chunk with page information
                    for i, chunk in enumerate(chunks):
                        chunk_metadata = {
                            **base_metadata,
                            "page_number": page_num + 1,
                            "chunk_index": i,
                            "chunks_in_page": len(chunks)
                        }
                        memory = self.create(category, chunk, chunk_metadata)
                        memory_ids.append(memory.id)

                return memory_ids
        except Exception as e:
            raise Exception(f"Failed to process PDF: {str(e)}")

    def _smart_chunk_text(self, text: str, chunk_size: int) -> List[str]:
        """Break text into chunks while trying to maintain logical boundaries"""
        chunks = []
        
        # Split by paragraphs
        paragraphs = [p for p in text.split('\n\n') if p.strip()]
        
        current_chunk = []
        current_size = 0
        
        for paragraph in paragraphs:
            paragraph_size = len(paragraph)
            
            # If this paragraph alone exceeds chunk size, split it by sentences
            if paragraph_size > chunk_size:
                sentences = [s.strip() for s in paragraph.split('.') if s.strip()]
                for sentence in sentences:
                    if len(sentence) > chunk_size:
                        # If a sentence is too long, split by words
                        words = sentence.split()
                        temp_chunk = []
                        temp_size = 0
                        for word in words:
                            if temp_size + len(word) > chunk_size:
                                chunks.append(' '.join(temp_chunk))
                                temp_chunk = [word]
                                temp_size = len(word)
                            else:
                                temp_chunk.append(word)
                                temp_size += len(word) + 1
                        if temp_chunk:
                            chunks.append(' '.join(temp_chunk))
                    else:
                        current_size += len(sentence)
                        if current_size > chunk_size:
                            chunks.append('. '.join(current_chunk) + '.')
                            current_chunk = [sentence]
                            current_size = len(sentence)
                        else:
                            current_chunk.append(sentence)
            else:
                if current_size + paragraph_size > chunk_size:
                    chunks.append('. '.join(current_chunk) + '.')
                    current_chunk = [paragraph]
                    current_size = paragraph_size
                else:
                    current_chunk.append(paragraph)
                    current_size += paragraph_size
        
        # Add the last chunk if there is one
        if current_chunk:
            chunks.append('. '.join(current_chunk) + '.')
        
        return chunks
    
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