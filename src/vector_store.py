# vector_store.py
"""Vector-store MCP tool implementations (require an embedding provider).

`VectorToolsMixin` provides create/list/delete/insert/search operations over
MariaDB ``VECTOR`` tables. It builds on `StandardToolsMixin` (inherited) for
``create_database`` and the existence/query helpers.

The module-level ``embedding_service`` singleton is created once at import when
``EMBEDDING_PROVIDER`` is configured (matching the previous behavior in
``server.py``); all vector tools share it. Embedding API calls are rate-limited
by ``self._embedding_semaphore`` (set during pool initialization).
"""

import json
from typing import Any

from config import EMBEDDING_PROVIDER, logger
from embeddings import EmbeddingService
from tools import StandardToolsMixin

# Singleton instance for embedding service (only when a provider is configured)
embedding_service: EmbeddingService | None = None
if EMBEDDING_PROVIDER is not None:
    embedding_service = EmbeddingService()


class VectorToolsMixin(StandardToolsMixin):
    """Vector-store tools: create, list, delete, insert, and semantic search."""

    async def create_vector_store(
        self,
        database_name: str,
        vector_store_name: str,
        model_name: str | None = None,
        distance_function: str | None = None,
    ) -> dict:
        """
        This tool creates a table which stores embeddings.

        Creates a new vector store (table) with a predefined schema if it doesn't already exist.
        It first checks if the database exists, creating it if necessary.
        Then, it checks if the table exists; if so, it reports that.
        Otherwise, it creates the table with id, document, embedding (VECTOR type), and metadata (JSON) columns.
        A VECTOR INDEX is created on the embedding column.

        Parameters:
        - database_name (str): The target database.
        - vector_store_name (str): The name of the table to create.
        - embedding_service: An instance of EmbeddingService to get model details.
        - model_name (str, optional): The embedding model to use (defaults to service default).
        - distance_function (str, optional): 'euclidean' or 'cosine'. Defaults to 'cosine'.
        """
        if embedding_service is None:
            raise RuntimeError("Embedding service not initialized. Ensure EMBEDDING_PROVIDER is configured.")
        return await self.create_vector_store_tool(
            database_name, vector_store_name, embedding_service, model_name, distance_function
        )

    async def create_vector_store_tool(
        self,
        database_name: str,
        vector_store_name: str,
        embedding_service: EmbeddingService,
        model_name: str | None = None,
        distance_function: str | None = None,
    ) -> dict[str, Any]:
        """
        This tool creates a new table which stores embeddings.

        Creates a new vector store (table) with a predefined schema if it doesn't already exist.
        It first checks if the database exists, creating it if necessary.
        Then, it checks if the table exists; if so, it reports that.
        Otherwise, it creates the table with id, document, embedding (VECTOR type), and metadata (JSON) columns.
        A VECTOR INDEX is created on the embedding column.

        Parameters:
        - database_name (str): The target database.
        - vector_store_name (str): The name of the table to create.
        - embedding_service: An instance of EmbeddingService to get model details.
        - model_name (str, optional): The embedding model to use (defaults to service default).
        - distance_function (str, optional): 'euclidean' or 'cosine'. Defaults to 'cosine'.
        """
        embedding_length = await embedding_service.get_embedding_dimension(model_name)
        logger.info(
            f"TOOL START: create_vector_store called. DB: '{database_name}', Store: '{vector_store_name}', Model: '{model_name}', Embedding_Length: {embedding_length}, Distance_Requested: '{distance_function}'"
        )

        # --- Input Validation ---
        if not database_name or not database_name.isidentifier():
            logger.error(f"Invalid database_name: '{database_name}'. Must be a valid identifier.")
            raise ValueError(f"Invalid database_name: '{database_name}'. Must be a valid identifier.")
        if not vector_store_name or not vector_store_name.isidentifier():
            logger.error(f"Invalid vector_store_name: '{vector_store_name}'. Must be a valid identifier.")
            raise ValueError(f"Invalid vector_store_name: '{vector_store_name}'. Must be a valid identifier.")

        if not isinstance(embedding_length, int) or embedding_length <= 0:
            logger.error(f"Invalid embedding_length: {embedding_length}. Must be a positive integer.")
            raise ValueError(f"Invalid embedding_length: {embedding_length}. Must be a positive integer.")

        # Validate and set distance_function
        valid_distance_functions_map = {"euclidean": "EUCLIDEAN", "cosine": "COSINE"}
        processed_distance_function_sql = valid_distance_functions_map["cosine"]  # Default

        if distance_function:
            df_lower = distance_function.lower()
            if df_lower in valid_distance_functions_map:
                processed_distance_function_sql = valid_distance_functions_map[df_lower]
            else:
                logger.error(
                    f"Invalid distance_function: '{distance_function}'. Must be one of {list(valid_distance_functions_map.keys())}."
                )
                raise ValueError(
                    f"Invalid distance_function: '{distance_function}'. Must be one of {list(valid_distance_functions_map.keys())}."
                )
        else:
            logger.info(f"Distance function not provided, defaulting to '{processed_distance_function_sql}'.")

        logger.info(f"Using SQL distance function: '{processed_distance_function_sql}'.")

        # --- Database Existence Check ---
        if not await self._database_exists(database_name):
            logger.info(f"Database '{database_name}' does not exist. Attempting to create it.")
            try:
                await self.create_database(database_name)
            except Exception as db_create_e:
                logger.error(f"Failed to ensure database '{database_name}' existence: {db_create_e}", exc_info=True)
                raise RuntimeError(
                    f"Failed to ensure database '{database_name}' exists before creating vector store. Reason: {str(db_create_e)}"
                ) from db_create_e

        # --- Table Existence Check ---
        if await self._table_exists(database_name, vector_store_name):
            message = f"Vector store (table) '{vector_store_name}' already exists in database '{database_name}'. No action taken."
            logger.info(f"TOOL END: create_vector_store. {message}")
            return {
                "status": "exists",
                "message": message,
                "database_name": database_name,
                "vector_store_name": vector_store_name,
            }

        # --- SQL Query for Vector Store Table Creation ---
        schema_query = f"""
        CREATE TABLE IF NOT EXISTS `{vector_store_name}` (
            id VARCHAR(36) NOT NULL DEFAULT UUID_v7() PRIMARY KEY,
            document TEXT NOT NULL,
            embedding VECTOR({embedding_length}) NOT NULL,
            metadata JSON NOT NULL,
            VECTOR INDEX (embedding) DISTANCE={processed_distance_function_sql}
        );
        """

        try:
            # --- Execute Query ---
            await self._execute_query(schema_query, database=database_name)

            success_message = f"Vector store '{vector_store_name}' created successfully in database '{database_name}' with {processed_distance_function_sql} distance."
            logger.info(f"TOOL END: create_vector_store completed. {success_message}")
            return {
                "status": "success",
                "message": success_message,
                "database_name": database_name,
                "vector_store_name": vector_store_name,
            }
        except Exception as e:
            error_message = f"Failed to create vector store '{vector_store_name}' in database '{database_name}'."
            logger.error(f"TOOL ERROR: create_vector_store failed. {error_message} Error: {e}", exc_info=True)
            raise RuntimeError(f"{error_message} Reason: {str(e)}") from e

    async def list_vector_stores(self, database_name: str) -> list[str]:
        """
        Lists all tables within the specified database that are identified as vector stores.
        A table is considered a vector store if it contains an indexed column named 'embedding'
        with a data type of 'VECTOR'.

        Parameters:
        - database_name (str): The name of the database to scan.

        Returns:
        - List[str]: A list of table names that are identified as vector stores.
                     Returns an empty list if no such tables are found or if the database doesn't exist.

        Raises:
        - ValueError: If the database_name is invalid.
        - RuntimeError: For database errors during the operation.
        """
        logger.info(f"TOOL START: list_vector_stores called for database: '{database_name}'")

        # --- Input Validation ---
        if not database_name or not database_name.isidentifier():
            logger.error(f"Invalid database_name: '{database_name}'. Must be a valid identifier.")
            raise ValueError(f"Invalid database_name: '{database_name}'. Must be a valid identifier.")

        if not await self._database_exists(database_name):
            logger.warning(f"Database '{database_name}' does not exist. Cannot list vector stores.")
            return []

        # --- SQL Query ---
        # This query identifies tables that have:
        # 1. A column named 'embedding'.
        # 2. The data type of this 'embedding' column is 'VECTOR'.
        # 3. This 'embedding' column is part of an index (ensured by the JOIN with STATISTICS).
        sql_query = """
        SELECT DISTINCT T1.TABLE_NAME
        FROM information_schema.COLUMNS AS T1
        INNER JOIN information_schema.STATISTICS AS T2
            ON T1.TABLE_SCHEMA = T2.TABLE_SCHEMA
            AND T1.TABLE_NAME = T2.TABLE_NAME
            AND T1.COLUMN_NAME = T2.COLUMN_NAME
        WHERE T1.TABLE_SCHEMA = %s
          AND UPPER(T1.COLUMN_NAME) = 'EMBEDDING'
          AND UPPER(T1.DATA_TYPE) = 'VECTOR'
        ORDER BY T1.TABLE_NAME;
        """

        try:
            results = await self._execute_query(sql_query, params=(database_name,), database="information_schema")

            store_list = [row["TABLE_NAME"] for row in results if "TABLE_NAME" in row]

            if not store_list:
                logger.info(f"No vector stores found in database '{database_name}'.")
            else:
                logger.info(f"Found {len(store_list)} vector store(s) in database '{database_name}': {store_list}")

            logger.info(f"TOOL END: list_vector_stores completed for database '{database_name}'.")
            return store_list

        except Exception as e:
            error_message = f"Failed to list vector stores in database '{database_name}'."
            logger.error(f"TOOL ERROR: list_vector_stores. {error_message} Error: {e}", exc_info=True)
            raise RuntimeError(f"{error_message} Reason: {str(e)}") from e

    async def delete_vector_store(self, database_name: str, vector_store_name: str) -> dict[str, Any]:
        """
        Deletes a vector store (table) from the specified database.
        It first verifies if the database and table exist, and if the table
        conforms to the definition of a vector store (contains an indexed 'embedding'
        column of type VECTOR).

        Parameters:
        - database_name (str): The name of the database.
        - vector_store_name (str): The name of the vector store table to delete.

        Returns:
        - Dict[str, Any]: A dictionary containing the status and a message.
                          Possible statuses: "success", "not_found", "not_vector_store", "error".
        """
        logger.info(f"TOOL START: delete_vector_store called for: '{database_name}.{vector_store_name}'")

        # --- Input Validation for names ---
        if not database_name or not database_name.isidentifier():
            logger.error(f"Invalid database_name: '{database_name}'. Must be a valid identifier.")
            raise ValueError(f"Invalid database_name: '{database_name}'. Must be a valid identifier.")
        if not vector_store_name or not vector_store_name.isidentifier():
            logger.error(f"Invalid vector_store_name: '{vector_store_name}'. Must be a valid identifier.")
            raise ValueError(f"Invalid vector_store_name: '{vector_store_name}'. Must be a valid identifier.")

        # --- Database Existence Check ---
        if not await self._database_exists(database_name):
            message = f"Database '{database_name}' does not exist. Cannot delete vector store."
            logger.warning(message)
            return {"status": "not_found", "message": message, "type": "database"}

        # --- Table Existence Check ---
        if not await self._table_exists(database_name, vector_store_name):
            message = f"Vector store (table) '{vector_store_name}' does not exist in database '{database_name}'."
            logger.warning(message)
            return {"status": "not_found", "message": message, "type": "table"}

        # --- Vector Store Verification ---
        if not await self._is_vector_store(database_name, vector_store_name):
            message = f"Table '{vector_store_name}' in database '{database_name}' is not a valid vector store (missing indexed 'embedding' column of type VECTOR). Deletion aborted."
            logger.warning(message)
            return {"status": "not_vector_store", "message": message}

        # --- SQL Query for Deletion ---
        drop_query = f"DROP TABLE IF EXISTS `{vector_store_name}`;"

        try:
            await self._execute_query(drop_query, database=database_name)

            success_message = (
                f"Vector store '{vector_store_name}' deleted successfully from database '{database_name}'."
            )
            logger.info(f"TOOL END: delete_vector_store. {success_message}")
            return {
                "status": "success",
                "message": success_message,
                "database_name": database_name,
                "vector_store_name": vector_store_name,
            }
        except Exception as e:
            error_message = f"Failed to delete vector store '{vector_store_name}' from database '{database_name}'."
            logger.error(f"TOOL ERROR: delete_vector_store. {error_message} Error: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"{error_message} Reason: {str(e)}",
                "database_name": database_name,
                "vector_store_name": vector_store_name,
            }

    async def insert_docs_vector_store(
        self,
        database_name: str,
        vector_store_name: str,
        documents: list[str],
        metadata: list[dict] | None = None,
        batch_size: int = 100,
    ) -> dict:
        """
        Insert a batch of documents (with optional metadata) into a vector store.
        Documents must be a non-empty list of strings. Metadata, if provided, must be a list of dicts of the same length as documents.
        If metadata is not provided, an empty dict will be used for each document.

        Args:
            database_name: Target database
            vector_store_name: Target vector store table
            documents: List of document strings to insert
            metadata: Optional list of metadata dicts (same length as documents)
            batch_size: Number of documents to insert per batch (default 100)
        """
        logger.info(
            f"TOOL START: insert_docs_vector_store called for {database_name}.{vector_store_name} with {len(documents)} documents"
        )

        if not database_name or not database_name.isidentifier():
            logger.error(f"Invalid database_name: '{database_name}'")
            raise ValueError(f"Invalid database_name: '{database_name}'")
        if not vector_store_name or not vector_store_name.isidentifier():
            logger.error(f"Invalid vector_store_name: '{vector_store_name}'")
            raise ValueError(f"Invalid vector_store_name: '{vector_store_name}'")
        if (
            not isinstance(documents, list)
            or not documents
            or not all(isinstance(doc, str) and doc for doc in documents)
        ):
            logger.error("'documents' must be a non-empty list of non-empty strings.")
            raise ValueError("'documents' must be a non-empty list of non-empty strings.")

        # Handle metadata: optional
        if metadata is None:
            metadata = [{} for _ in documents]
        if not isinstance(metadata, list) or len(metadata) != len(documents):
            logger.error("'metadata' must be a list of dicts, same length as documents (or omitted).")
            raise ValueError("'metadata' must be a list of dicts, same length as documents (or omitted).")

        inserted = 0
        errors = []

        # Process in batches for better performance
        for batch_start in range(0, len(documents), batch_size):
            batch_end = min(batch_start + batch_size, len(documents))
            batch_docs = documents[batch_start:batch_end]
            batch_meta = metadata[batch_start:batch_end]

            try:
                # Generate embeddings with rate limiting
                if embedding_service is None:
                    raise RuntimeError("Embedding service not initialized. Ensure EMBEDDING_PROVIDER is configured.")
                if self._embedding_semaphore:
                    async with self._embedding_semaphore:
                        embeddings = await embedding_service.embed(batch_docs)
                        self._metrics["embeddings_generated"] += len(batch_docs)
                else:
                    embeddings = await embedding_service.embed(batch_docs)
                    self._metrics["embeddings_generated"] += len(batch_docs)

                # Prepare metadata JSON
                metadata_json = [json.dumps(m) for m in batch_meta]

                # Build batch INSERT query for better performance
                insert_query = f"INSERT INTO `{database_name}`.`{vector_store_name}` (document, embedding, metadata) VALUES (%s, VEC_FromText(%s), %s)"

                # Insert each document (MariaDB doesn't support batch vector inserts well)
                for doc, emb, meta in zip(batch_docs, embeddings, metadata_json, strict=False):
                    emb_str = json.dumps(emb)
                    try:
                        await self._execute_query(
                            insert_query, params=(doc, emb_str, meta), database=database_name, limit_results=False
                        )
                        inserted += 1
                    except Exception as e:
                        logger.error(f"Failed to insert doc into {database_name}.{vector_store_name}: {e}")
                        errors.append(str(e))

            except Exception as e:
                logger.error(f"Failed to process batch {batch_start}-{batch_end}: {e}", exc_info=True)
                errors.append(f"Batch {batch_start}-{batch_end}: {str(e)}")

        logger.info(
            f"TOOL END: insert_docs_vector_store. Inserted {inserted}/{len(documents)} documents (errors: {len(errors)})"
        )
        result: dict[str, Any] = {
            "status": "success" if inserted == len(documents) else "partial",
            "inserted": inserted,
            "total": len(documents),
        }
        if errors:
            result["errors"] = errors[:10]  # Limit error messages to avoid huge responses
            if len(errors) > 10:
                result["errors_truncated"] = len(errors) - 10
        return result

    async def search_vector_store(
        self, user_query: str, database_name: str, vector_store_name: str, k: int = 7
    ) -> list:
        """
        Search a vector store for the most similar documents to a query using semantic search.

        Args:
            user_query: The search query string.
            database_name: The database name.
            vector_store_name: The vector store (table) name.
            k: Number of top results to retrieve (default 7).

        Returns:
            List of dicts with document, metadata, and distance.
        """
        logger.info(f"TOOL START: search_vector_store called for {database_name}.{vector_store_name}")

        # Input validation
        if not user_query or not isinstance(user_query, str):
            logger.error("user_query must be a non-empty string.")
            raise ValueError("user_query must be a non-empty string.")
        if not database_name or not database_name.isidentifier():
            logger.error(f"Invalid database_name: '{database_name}'")
            raise ValueError(f"Invalid database_name: '{database_name}'")
        if not vector_store_name or not vector_store_name.isidentifier():
            logger.error(f"Invalid vector_store_name: '{vector_store_name}'")
            raise ValueError(f"Invalid vector_store_name: '{vector_store_name}'")
        if not isinstance(k, int) or k <= 0:
            logger.error("k must be a positive integer.")
            raise ValueError("k must be a positive integer.")

        # Generate embedding for the query with rate limiting
        if embedding_service is None:
            raise RuntimeError("Embedding service not initialized. Ensure EMBEDDING_PROVIDER is configured.")
        if self._embedding_semaphore:
            async with self._embedding_semaphore:
                embedding = await embedding_service.embed(user_query)
                self._metrics["embeddings_generated"] += 1
        else:
            embedding = await embedding_service.embed(user_query)
            self._metrics["embeddings_generated"] += 1

        emb_str = json.dumps(embedding)

        # Prepare the search query
        search_query = f"""
            SELECT
                document,
                metadata,
                VEC_DISTANCE_COSINE(embedding, VEC_FromText(%s)) AS distance
            FROM `{database_name}`.`{vector_store_name}`
            ORDER BY distance ASC
            LIMIT %s
        """
        try:
            results = await self._execute_query(
                search_query, params=(emb_str, k), database=database_name, limit_results=False
            )
            for row in results:
                if isinstance(row.get("metadata"), str):
                    try:
                        row["metadata"] = json.loads(row["metadata"])
                    except json.JSONDecodeError as e:
                        raw_meta = row.get("metadata") or ""
                        logger.warning(
                            f"Failed to parse metadata JSON for document: {e}. Raw value: {raw_meta[:100]}..."
                        )
                        # Keep raw string if parsing fails
            logger.info(f"TOOL END: search_vector_store. Returned {len(results)} results.")
            return results
        except Exception as e:
            logger.error(f"Failed to search vector store {database_name}.{vector_store_name}: {e}", exc_info=True)
            raise RuntimeError(f"Vector store search failed: {e}") from e
