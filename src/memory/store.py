from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from typing import Dict, List, Optional
from .types import Memory, SearchResult
import logging
import math
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self, agent_name: str):

        # Create agent-specific directory
        from pathlib import Path
        self.db_path = Path(f"./memory_db/{agent_name}")
        self.db_path.parent.mkdir(exist_ok=True)  # Create memory_db if it doesn't exist
        
        # Create a persistent client with agent-specific path
        self.client = PersistentClient(path=str(self.db_path))

        self.collections = {}

        # Load existing collections
        try:
            collection_names = self.client.list_collections()
            for name in collection_names:
                try:
                    self.collections[name] = self.client.get_collection(name)
                except Exception as e:
                    logger.error(f"Error loading collection {name}: {e}")
        except Exception as e:
            logger.error(f"Error loading existing collections: {e}")

    def _clean_metadata(self, metadata: Dict) -> Dict:
        """Clean metadata to ensure all values are ChromaDB-compatible types"""
        cleaned = {}
        for key, value in metadata.items():
            # Convert None to empty string
            if value is None:
                cleaned[key] = ""
            # Convert any other values to strings if they're not primitive types
            elif not isinstance(value, (str, int, float, bool)):
                cleaned[key] = str(value)
            else:
                cleaned[key] = value
        return cleaned

    def add(self, category: str, content: str, metadata: Dict) -> Memory:
        """Add a new memory to the store"""
        if category not in self.collections:
            self.collections[category] = self.client.create_collection(category)
        
        collection = self.collections[category]
        memory_id = str(len(collection.get()['ids']) + 1)
        
        try:
            # Clean metadata before adding
            clean_metadata = self._clean_metadata(metadata)
            
            collection.add(
                documents=[content],
                metadatas=[clean_metadata],
                ids=[memory_id]
            )
            
            return Memory(
                id=memory_id,
                content=content,
                category=category,
                metadata=metadata  # Return original metadata in Memory object
            )
        except Exception as e:
            logger.error(f"Error adding document to collection: {e}")
            raise e

    def search(
        self, 
        category: str,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict] = None
    ) -> List[SearchResult]:
        """Search for similar memories in a category"""
        if category not in self.collections:
            logger.error(f"Collection {category} not found")
            return []

        collection = self.collections[category]
        try:
            
            # Get collection size and adjust n_results
            total_docs = len(collection.get()['ids'])
            if total_docs == 0:
                logger.error("Collection is empty")
                return []
                
            # Adjust n_results before query
            n_results = min(n_results, total_docs)
            logger.info(f"Searching {total_docs} documents for query: '{query}'")
            
            # Perform search with debug info
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filter_metadata,
                include=['distances', 'documents', 'metadatas']
            )
            
            # Debug info without trying to log embeddings directly
            logger.info("\nQuery results structure:")
            logger.info(f"Available keys: {results.keys()}")
            
            # Process results
            search_results = []
            for i in range(len(results['ids'][0])):
                memory = Memory(
                    id=results['ids'][0][i],
                    content=results['documents'][0][i],
                    category=category,
                    metadata=results['metadatas'][0][i]
                )
                
                # Calculate similarity score
                distance = float(results['distances'][0][i])
                # Use exponential normalization for better score distribution
                similarity_score = math.exp(-distance)
                
                logger.info(f"\nResult {i+1}:")
                logger.info(f"Raw distance: {distance}")
                logger.info(f"Normalized similarity: {similarity_score}")
                logger.info(f"Content preview: '{results['documents'][0][i][:100]}'")
                
                search_results.append(SearchResult(
                    memory=memory,
                    similarity_score=similarity_score
                ))
            
            return search_results
                
        except Exception as e:
            logger.error(f"Error searching collection {category}: {e}")
            logger.error(f"Exception type: {type(e)}")
            return []

    def get_recent(
        self,
        category: str,
        n_results: int = 10,
        filter_metadata: Optional[Dict] = None
    ) -> List[Memory]:
        """Get most recent memories from a category"""
        if category not in self.collections:
            return []
            
        collection = self.collections[category]
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
        if category not in self.collections:
            try:
                # Use default embedding function
                from chromadb.utils import embedding_functions
                default_ef = embedding_functions.DefaultEmbeddingFunction()
                
                try:
                    self.collections[category] = self.client.get_collection(
                        name=category,
                        embedding_function=default_ef
                    )
                except:
                    self.collections[category] = self.client.create_collection(
                        name=category,
                        embedding_function=default_ef
                    )
            except Exception as e:
                logger.error(f"Error creating/getting collection {category}: {e}")
                raise e
                
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
        
    def list_categories(self) -> List[str]:
        """List all categories"""
        return list(self.collections.keys())
    
    def diagnose_collection(self, category: str) -> Dict:
        """Diagnose the state of a collection"""
        if category not in self.collections:
            return {"status": "missing", "error": "Collection not found"}
            
        collection = self.collections[category]
        try:
            # Get raw collection data
            data = collection.get()
            return {
                "status": "ok",
                "count": len(data['ids']),
                "has_embeddings": 'embeddings' in data,
                "sample_ids": data['ids'][:3],
                "sample_metadata": data['metadatas'][:3] if data['metadatas'] else None,
                "raw_data": data
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}