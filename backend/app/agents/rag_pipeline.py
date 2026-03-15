"""RAG pipeline for recipe retrieval using ChromaDB vector store."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from app.agents.rt_config import get_vector_store, is_railtracks_enabled
from app.core.config import get_settings
from app.services.planner import retrieve_recipe_candidates
from app.schemas.contracts import ConstraintSet, InventorySnapshot


class RAGPipeline:
    """Retrieval-Augmented Generation pipeline for semantic recipe search.

    This class provides:
    - Indexing of recipes into ChromaDB for semantic search
    - Context retrieval based on user inventory and constraints
    - Keyword retrieval path when vector search is unavailable
    """

    def __init__(self) -> None:
        """Initialize RAG pipeline with vector store."""
        settings = get_settings()
        self._vector_store_mode = settings.vector_store_mode
        self._snapshot_path = Path(settings.vector_snapshot_path).expanduser()
        self._enabled = is_railtracks_enabled()
        self._vector_store = None
        self._indexed = False

        if self._enabled:
            try:
                self._vector_store = get_vector_store()
            except Exception:
                self._enabled = False

        if self._enabled and self._vector_store and self._vector_store_mode == "memory":
            snapshot_recipes = self._load_snapshot_recipes()
            if snapshot_recipes:
                try:
                    self._index_recipes(snapshot_recipes)
                    self._indexed = True
                except Exception:
                    # Snapshot hydration should never block startup.
                    self._indexed = False

    def initialize(self, recipes: list[dict[str, Any]] | None = None) -> bool:
        """Index recipes into ChromaDB for semantic retrieval.

        Args:
            recipes: Optional list of recipe dictionaries to index. If None,
                    attempts to fetch sample recipes from TheMealDB.

        Returns:
            True if indexing succeeded or was already complete, False otherwise.
        """
        if not self._enabled or not self._vector_store:
            return False

        if self._indexed:
            return True

        try:
            if recipes is None:
                if self._vector_store_mode == "memory":
                    recipes = self._load_snapshot_recipes()
                if not recipes:
                    recipes = self._fetch_sample_recipes()

            if not recipes:
                return False

            self._index_recipes(recipes)
            if self._vector_store_mode == "memory":
                self._persist_snapshot_recipes(recipes)
            self._indexed = True
            return True
        except Exception:
            return False

    def _load_snapshot_recipes(self) -> list[dict[str, Any]]:
        """Load locally persisted recipe corpus for memory vector mode."""

        if not self._snapshot_path.exists():
            return []
        try:
            payload = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def _persist_snapshot_recipes(self, recipes: list[dict[str, Any]]) -> None:
        """Persist recipe corpus snapshot for local memory-mode bootstrap."""

        self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot_path.write_text(
            json.dumps(recipes, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _fetch_sample_recipes(self, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch sample recipes from TheMealDB for initial indexing.

        Args:
            limit: Maximum number of recipes to fetch.

        Returns:
            List of recipe dictionaries.
        """
        try:
            # Fetch diverse recipes using different search terms
            search_terms = ["chicken", "beef", "pasta", "vegetable", "soup"]
            recipes = []

            for term in search_terms[:3]:  # Limit API calls
                candidates = retrieve_recipe_candidates(
                    inventory=None,
                    constraints=None,
                    limit=limit // len(search_terms) + 1,
                )
                recipes.extend(candidates)
                if len(recipes) >= limit:
                    break

            return recipes[:limit]
        except Exception:
            return []

    def _index_recipes(self, recipes: list[dict[str, Any]]) -> None:
        """Index recipes into the vector store.

        Args:
            recipes: List of recipe dictionaries to index.
        """
        if not self._vector_store:
            return

        documents = []
        metadatas = []
        ids = []

        for recipe in recipes:
            recipe_id = recipe.get("recipe_id", f"recipe_{len(ids)}")
            recipe_title = recipe.get("recipe_title", "Unknown Recipe")
            ingredients = recipe.get("ingredients", [])
            instructions = recipe.get("instructions", "")
            category = recipe.get("category", "")
            area = recipe.get("area", "")
            tags = recipe.get("tags", [])

            # Create searchable text document
            doc_text = self._create_recipe_document(
                recipe_title=recipe_title,
                ingredients=ingredients,
                instructions=instructions,
                category=category,
                area=area,
                tags=tags,
            )

            documents.append(doc_text)
            metadatas.append(
                {
                    "recipe_id": recipe_id,
                    "recipe_title": recipe_title,
                    "category": category or "unknown",
                    "area": area or "unknown",
                    "ingredient_count": len(ingredients),
                    "tags": ",".join(tags) if tags else "",
                }
            )
            ids.append(recipe_id)

        if not documents or not self._vector_store:
            return

        if hasattr(self._vector_store, "add_texts"):
            self._vector_store.add_texts(
                texts=documents,
                metadatas=metadatas,
                ids=ids,
            )
            return

        # Railtracks >=1.x ChromaVectorStore API path.
        if hasattr(self._vector_store, "upsert"):
            from railtracks.vector_stores.vector_store_base import Chunk

            chunks = [
                Chunk(
                    content=documents[index],
                    id=ids[index],
                    metadata=metadatas[index],
                )
                for index in range(len(documents))
            ]
            self._vector_store.upsert(chunks)

    @staticmethod
    def _create_recipe_document(
        recipe_title: str,
        ingredients: list[str],
        instructions: str,
        category: str,
        area: str,
        tags: list[str],
    ) -> str:
        """Create a searchable text document from recipe fields.

        Args:
            recipe_title: Name of the recipe.
            ingredients: List of ingredients.
            instructions: Cooking instructions.
            category: Recipe category.
            area: Recipe cuisine area.
            tags: Recipe tags.

        Returns:
            Combined text document for embedding.
        """
        parts = [
            f"Recipe: {recipe_title}",
            f"Category: {category}" if category else "",
            f"Cuisine: {area}" if area else "",
            f"Ingredients: {', '.join(ingredients)}" if ingredients else "",
            f"Tags: {', '.join(tags)}" if tags else "",
            instructions[:500] if instructions else "",  # Truncate long instructions
        ]
        return "\n".join(filter(None, parts))

    def retrieve_context(
        self,
        inventory: InventorySnapshot | None = None,
        constraints: ConstraintSet | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant recipe context using semantic search.

        Args:
            inventory: User's current inventory for context.
            constraints: Dietary and preference constraints.
            limit: Maximum number of recipes to retrieve.

        Returns:
            List of relevant recipes with metadata, sorted by relevance.
        """
        if not self._enabled or not self._vector_store:
            return self._keyword_retrieve(inventory, constraints, limit)

        try:
            query = self._build_search_query(inventory, constraints)
            if not query:
                return self._keyword_retrieve(inventory, constraints, limit)

            if hasattr(self._vector_store, "similarity_search"):
                results = self._vector_store.similarity_search(
                    query=query,
                    k=limit,
                )
            elif hasattr(self._vector_store, "search"):
                results = self._vector_store.search(query=query, top_k=limit)
                if results and isinstance(results, list) and isinstance(results[0], list):
                    results = results[0]
            else:
                return self._keyword_retrieve(inventory, constraints, limit)

            recipes = []
            for doc in results:
                metadata = getattr(doc, "metadata", {})
                distance = getattr(doc, "distance", None)
                relevance_score = (
                    1.0 / (1.0 + float(distance))
                    if distance is not None
                    else getattr(doc, "score", 1.0)
                )
                recipes.append(
                    {
                        "recipe_id": metadata.get("recipe_id", ""),
                        "recipe_title": metadata.get("recipe_title", "Unknown"),
                        "category": metadata.get("category", ""),
                        "area": metadata.get("area", ""),
                        "relevance_score": relevance_score,
                        "source": "vector_search",
                    }
                )

            return recipes[:limit]
        except Exception:
            return self._keyword_retrieve(inventory, constraints, limit)

    @staticmethod
    def _build_search_query(
        inventory: InventorySnapshot | None,
        constraints: ConstraintSet | None,
    ) -> str:
        """Build search query from inventory and constraints.

        Args:
            inventory: User's current inventory.
            constraints: Dietary constraints.

        Returns:
            Combined search query string.
        """
        query_parts = []

        if inventory and inventory.items:
            # Separate critical-expiry from general inventory
            expiring = sorted(
                [item for item in inventory.items if item.expires_in_days is not None and item.expires_in_days <= 3],
                key=lambda x: x.expires_in_days or 999,
            )
            if expiring:
                names = ", ".join(item.ingredient for item in expiring[:4])
                query_parts.append(f"healthy recipe using {names}")

            # Add other available ingredients for broader context
            non_expiring = [
                item.ingredient for item in inventory.items
                if item.expires_in_days is None or item.expires_in_days > 3
            ]
            if non_expiring:
                query_parts.append(f"also has {', '.join(non_expiring[:4])}")

        if constraints:
            if constraints.dietary_restrictions:
                query_parts.append(f"{' '.join(constraints.dietary_restrictions)} recipes")
            if constraints.max_cook_time_minutes:
                query_parts.append("quick easy meals")

        return " ".join(query_parts) if query_parts else "easy healthy recipes"

    def _keyword_retrieve(
        self,
        inventory: InventorySnapshot | None,
        constraints: ConstraintSet | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Keyword-based recipe retrieval.

        Args:
            inventory: User's current inventory.
            constraints: Dietary constraints.
            limit: Maximum number of recipes to return.

        Returns:
            List of recipes with metadata.
        """
        recipes = retrieve_recipe_candidates(inventory, constraints, limit=limit)

        return [
            {
                "recipe_id": recipe.get("recipe_id", ""),
                "recipe_title": recipe.get("recipe_title", "Unknown"),
                "category": recipe.get("category", ""),
                "area": recipe.get("area", ""),
                "relevance_score": 1.0,
                "source": "keyword_search",
                "full_recipe": recipe,
            }
            for recipe in recipes
        ]


@lru_cache(maxsize=1)
def get_rag_pipeline() -> RAGPipeline:
    """Return cached RAG pipeline instance.

    Returns:
        Singleton RAGPipeline instance.
    """
    return RAGPipeline()
