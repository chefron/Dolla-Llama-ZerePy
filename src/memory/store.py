import chromadb
from typing import Dict, List, Optional
from .types import Memory, SearchResult
import logging
logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self):
        self.client = chromadb.Client()
        self.collections = {}

        # Load existing collections using the new API
        try:
            collection_names = self.client.list_collections()
            for name in collection_names:
                try:
                    self.collections[name] = self.client.get_collection(name)
                except Exception as e:
                    logger.error(f"Error loading collection {name}: {e}")
        except Exception as e:
            logger.error(f"Error loading existing collections: {e}")

    def add(self, category: str, content: str, metadata: Dict) -> Memory:
        if category not in self.collections:
            self.collections[category] = self.client.create_collection(category)
        
        collection = self.collections[category]
        memory_id = str(len(collection.get()['ids']) + 1)
        
        collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[memory_id]
        )
        
        return Memory(
            id=memory_id,
            content=content,
            category=category,
            metadata=metadata
        )
    
    def search(
        self, 
        category: str,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict] = None
    ) -> List[SearchResult]:
        """
        Search for similar memories in a category
        """
        if category not in self.collections:
            return []
    
        collection = self.collections[category]
    
        # Perform the search
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=filter_metadata,  # ChromaDB filtering
        )
    
        # Format results into SearchResult objects
        search_results = []
        for i in range(len(results['ids'][0])):
            memory = Memory(
                id=results['ids'][0][i],
                content=results['documents'][0][i],
                category=category,
                metadata=results['metadatas'][0][i],
            )
        
            # Calculate similarity score - lower distance means more similar
            distance = float(results['distances'][0][i]) if 'distances' in results else 1.0
            similarity_score = 1.0 - distance
        
            search_results.append(SearchResult(
                memory=memory,
                similarity_score=similarity_score
            ))
    
        return search_results

    def get_recent(
        self,
        category: str,
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None
    ) -> List[Memory]:
        """
        Get the most recent memories from a category
        """
        if category not in self.collections:
            return []
            
        collection = self.collections[category]
        
        # Get memories sorted by ID (since IDs are sequential)
        results = collection.get(
            where=filter_metadata,
            limit=n_results,
        )
        
        memories = []
        for i in range(len(results['ids'])):
            memories.append(Memory(
                id=results['ids'][i],
                content=results['documents'][i],
                category=category,
                metadata=results['metadatas'][i],
            ))
        
        return memories[::-1]  # Reverse to get most recent first
    
    def get(self, category: str, memory_id: str) -> Optional[Memory]:
        """Get a specific memory by ID"""
        if category not in self.collections:
            return None
            
        collection = self.collections[category]
        results = collection.get(
            ids=[memory_id]
        )
        
        if not results['ids']:
            return None
            
        return Memory(
            id=results['ids'][0],
            content=results['documents'][0],
            category=category,
            metadata=results['metadatas'][0]
        )

    def delete(self, category: str, memory_id: str) -> bool:
        """Delete a specific memory"""
        if category not in self.collections:
            return False
            
        collection = self.collections[category]
        try:
            collection.delete(
                ids=[memory_id]
            )
            return True
        except:
            return False

    def get_or_create_collection(self, category: str):
        """Get an existing collection or create it"""
        try:
            if category not in self.collections:
                try:
                    self.collections[category] = self.client.get_collection(category)
                except:
                    self.collections[category] = self.client.create_collection(category)
        except Exception as e:
            logger.error(f"Error accessing collection {category}: {e}")
        
        return self.collections[category]
    
    def get_or_create_collection(self, category: str):
        """Get an existing collection or create it"""
        if category not in self.collections:
            self.collections[category] = self.client.create_collection(category)
        return self.collections[category]

    def update(self, category: str, memory_id: str, content: Optional[str] = None, metadata: Optional[Dict] = None) -> bool:
        """Update a memory's content and/or metadata"""
        if category not in self.collections:
            return False
            
        collection = self.collections[category]
        
        try:
            if content:
                collection.update(
                    ids=[memory_id],
                    documents=[content],
                    metadatas=[metadata] if metadata else None
                )
            elif metadata:
                collection.update(
                    ids=[memory_id],
                    metadatas=[metadata]
                )
            return True
        except Exception:
            return False