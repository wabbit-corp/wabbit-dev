import os
import sqlite3
import time
import pickle
import logging
import inspect
import asyncio
import threading
import atexit
from functools import wraps
from hashlib import md5

logger = logging.getLogger(__name__)


# --- Sentinel for Conditional Caching ---
class NoCacheSentinel:
    def __repr__(self):
        return "NO_CACHE"


NO_CACHE = NoCacheSentinel()

###############################################################################
# Thread-Local Cashier Management & Cleanup
###############################################################################

_thread_local_storage = threading.local()
_global_cashier_registry = {}  # Map path -> Cashier instance
_registry_lock = threading.Lock()
_cleanup_registered = False


class Cashier:
    """
    (Docstring remains largely the same, focusing on storage and features)
    Cashier manages a local SQLite database for caching.
    - We store: key (md5), fqn, val (pickled blob), insert_time.
    - We do not store an explicit expiration. Instead, we rely on:
        * a TTL check at retrieval (default_ttl in the decorator), and
        * periodic cleanup of records older than `max_age` for the specific FQN (if set),
        * capacity-based eviction per FQN if `max_fqn_capacity` is set.
    """

    _CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS bucket (
        key TEXT PRIMARY KEY,
        fqn TEXT NOT NULL,
        val BLOB NOT NULL,
        insert_time FLOAT NOT NULL,
        specific_ttl FLOAT DEFAULT NULL
    );
    """
    # Add index for faster FQN lookups (cleanup, capacity checks)
    _CREATE_IDX_SQL = (
        "CREATE INDEX IF NOT EXISTS idx_fqn_insert_time ON bucket(fqn, insert_time);"
    )

    _GET_SQL = "SELECT val, insert_time, specific_ttl FROM bucket WHERE key = ?"
    _DEL_SQL = "DELETE FROM bucket WHERE key = ?"
    _SET_SQL = """
        INSERT OR REPLACE INTO bucket (key, fqn, val, insert_time, specific_ttl)
        VALUES (?, ?, ?, ?, ?)
    """
    _DEL_FQN_SQL = "DELETE FROM bucket WHERE fqn = ?"
    _COUNT_FQN_SQL = "SELECT COUNT(*) FROM bucket WHERE fqn = ?"
    _REMOVE_OLDEST_FQN_SQL = """
        DELETE FROM bucket
        WHERE key IN (
            SELECT key FROM bucket
            WHERE fqn = ?
            ORDER BY insert_time ASC
            LIMIT ?
        )
    """
    # *** MODIFIED: FQN-specific age cleanup ***
    _CLEANUP_AGE_FQN_SQL = "DELETE FROM bucket WHERE fqn = ? AND insert_time < ?"

    def __init__(self, path: str):
        """
        Initializes the Cashier. Should generally be accessed via get_cashier_instance.
        :param path: Absolute path to the SQLite file.
        """
        self.path = path  # Assume path is already absolute
        self._conn = None  # Initialize as None
        self._lock = threading.RLock()  # RLock for re-entrancy if needed

        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            # Single connection for the entire instance, check_same_thread=False needed for multi-thread access via factory
            self._conn = sqlite3.connect(self.path, timeout=60, check_same_thread=False)
            # Use WAL mode for better concurrency
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            with self._conn:
                self._conn.execute(self._CREATE_SQL)
                self._conn.execute(self._CREATE_IDX_SQL)  # Create index
            logger.debug("Cashier initialized with DB path: %s", self.path)
        except sqlite3.Error as e:
            logger.error(
                "Failed to initialize Cashier database at %s: %s",
                self.path,
                e,
                exc_info=True,
            )
            self._conn = None  # Ensure connection is None on error
            raise  # Propagate the error

    def _ensure_connection(self):
        """Checks if connection exists, raises error if not."""
        if self._conn is None:
            # This might happen if init failed or after close() was called
            raise sqlite3.Error(
                f"Cashier database connection is not available for path: {self.path}"
            )

    def close(self):
        """Closes the underlying SQLite connection and unregisters."""
        with self._lock:
            if self._conn:
                logger.debug("Closing DB connection for Cashier at path: %s", self.path)
                try:
                    self._conn.close()
                except sqlite3.Error as e:
                    logger.error(
                        "Error closing connection for %s: %s",
                        self.path,
                        e,
                        exc_info=True,
                    )
                finally:
                    self._conn = None  # Mark as closed
                    # Unregister from global cleanup
                    unregister_cashier_globally(self.path)

    def delete_by_key(self, key: str):
        logger.debug("Deleting key from cache: %s (db=%s)", key, self.path)
        with self._lock:
            self._ensure_connection()
            with self._conn:
                self._conn.execute(self._DEL_SQL, (key,))

    def delete_by_fqn(self, fqn: str):
        logger.debug("Deleting all entries by fqn: %s (db=%s)", fqn, self.path)
        with self._lock:
            self._ensure_connection()
            with self._conn:
                self._conn.execute(self._DEL_FQN_SQL, (fqn,))

    def get(self, key: str, default_ttl: float = None):
        """
        Retrieve cached object. Prioritizes TTL stored with item over default_ttl.
        """
        logger.debug("Attempting to get key from cache: %s (db=%s)", key, self.path)
        with self._lock:
            self._ensure_connection()
            cursor = self._conn.cursor()
            cursor.execute(self._GET_SQL, (key,))
            row = cursor.fetchone()
            if not row:
                logger.debug("Cache miss - key not found: %s", key)
                return None

            val_blob, insert_time, stored_ttl = row  # Unpack stored TTL

            # Determine effective TTL: stored TTL overrides default
            effective_ttl = default_ttl
            if stored_ttl is not None:
                effective_ttl = stored_ttl
                logger.debug(
                    "Using specific stored TTL=%.1f for key %s", stored_ttl, key
                )
            elif default_ttl is not None:
                logger.debug("Using default TTL=%.1f for key %s", default_ttl, key)

            # Check expiration using effective TTL
            if effective_ttl is not None:
                now = time.time()
                if (now - insert_time) > effective_ttl:
                    logger.debug(
                        "Key %s expired (insert=%.1f, now=%.1f, effective_ttl=%.1f). Deleting.",
                        key,
                        insert_time,
                        now,
                        effective_ttl,
                    )
                    # Perform deletion within the same transaction lock
                    with self._conn:
                        self._conn.execute(self._DEL_SQL, (key,))
                    return None

            logger.debug("Cache hit for key: %s", key)
            return pickle.loads(val_blob)

    def set(
        self,
        key: str,
        fqn: str,
        val: bytes,  # Expect pickled blob
        max_age: float = None,
        max_fqn_capacity: int = None,
        specific_ttl: float = None,
    ):
        logger.debug(
            "Setting key in cache: %s (fqn=%s, db=%s, specific_ttl=%s)",
            key,
            fqn,
            self.path,
            specific_ttl,
        )
        now = time.time()

        with self._lock:
            self._ensure_connection()
            # Use a single transaction for set and potential cleanup
            with self._conn:
                # Insert or replace
                self._conn.execute(self._SET_SQL, (key, fqn, val, now, specific_ttl))

                # 1) FQN-Scoped Age-based cleanup
                if max_age is not None:
                    cutoff = now - max_age
                    logger.debug(
                        "Cleaning up items older than %.1f seconds for fqn=%s",
                        max_age,
                        fqn,
                    )
                    # *** MODIFIED: Use FQN-specific cleanup SQL ***
                    deleted_rows = self._conn.execute(
                        self._CLEANUP_AGE_FQN_SQL,  # Use the FQN specific query
                        (fqn, cutoff),  # Pass FQN and cutoff time
                    ).rowcount
                    if deleted_rows > 0:
                        logger.debug(
                            "Removed %d old items via max_age for fqn=%s",
                            deleted_rows,
                            fqn,
                        )

                # 2) Capacity-based cleanup for this FQN
                if max_fqn_capacity is not None and max_fqn_capacity > 0:
                    # Check count *after* potential age-based cleanup
                    cursor = self._conn.cursor()
                    cursor.execute(self._COUNT_FQN_SQL, (fqn,))
                    count_row = cursor.fetchone()
                    count = count_row[0] if count_row else 0

                    if count > max_fqn_capacity:
                        to_remove = count - max_fqn_capacity
                        logger.debug(
                            "FQN capacity exceeded (have=%d, max=%d). Removing %d oldest entries for fqn=%s",
                            count,
                            max_fqn_capacity,
                            to_remove,
                            fqn,
                        )
                        self._conn.execute(
                            self._REMOVE_OLDEST_FQN_SQL, (fqn, to_remove)
                        )


# --- Cashier Factory and Cleanup Registration ---


def get_cashier_instance(path: str) -> Cashier:
    """
    Gets or creates a Cashier instance for the given path.
    Manages instances globally but ensures thread-local access semantics if needed indirectly.
    Creates one instance per path for the entire application.
    """
    global _cleanup_registered
    abs_path = os.path.abspath(path)

    with _registry_lock:
        if abs_path not in _global_cashier_registry:
            logger.debug("Creating new shared Cashier instance for path: %s", abs_path)
            try:
                instance = Cashier(path=abs_path)
                _global_cashier_registry[abs_path] = instance

                # Register cleanup hook ONCE, when the first Cashier is made
                if not _cleanup_registered:
                    atexit.register(_cleanup_all_cashiers)
                    _cleanup_registered = True
                    logger.debug(
                        "atexit cleanup function registered for Cashier instances."
                    )

            except Exception as e:
                # Log error during creation, but let exception propagate
                logger.error(
                    "Failed to create Cashier instance for path %s: %s", abs_path, e
                )
                raise  # Propagate creation error

        # Return the instance associated with the path
        # If creation failed above, this line won't be reached for that path
        # If it existed before, or creation succeeded, return it
        if abs_path in _global_cashier_registry:
            return _global_cashier_registry[abs_path]
        else:
            # Should not happen if exception handling is correct, but as a safeguard:
            raise RuntimeError(
                f"Failed to get or create Cashier instance for {abs_path}"
            )


def unregister_cashier_globally(abs_path: str):
    """Removes a cashier instance from the global registry (called by Cashier.close)."""
    with _registry_lock:
        if abs_path in _global_cashier_registry:
            del _global_cashier_registry[abs_path]
            logger.debug("Unregistered Cashier instance for path: %s", abs_path)


def _cleanup_all_cashiers():
    """Function called by atexit to close all managed cashier connections."""
    logger.debug("Closing all registered Cashier database connections via atexit...")
    # Create a copy of instances to close, as closing modifies the registry
    instances_to_close = []
    with _registry_lock:
        instances_to_close = list(_global_cashier_registry.values())

    if not instances_to_close:
        logger.debug("No active Cashier instances to close.")
        return

    for instance in instances_to_close:
        try:
            logger.debug("atexit: Closing Cashier for DB: %s", instance.path)
            instance.close()  # This will also attempt to unregister
        except Exception as e:
            # Log error during cleanup, but continue closing others
            logger.error(
                "atexit: Error closing Cashier for DB %s: %s",
                instance.path,
                e,
                exc_info=True,
            )
    logger.debug("Finished closing Cashier connections via atexit.")


###############################################################################
# Helpers
###############################################################################
def _get_fqn(fn):
    """Gets the fully qualified name for a callable."""
    return f"{fn.__module__}.{fn.__qualname__}"


def _build_cache_key(fqn, func_sig, args, kwargs, exclude_params):
    """Builds a deterministic cache key from function and arguments."""
    try:
        bound = func_sig.bind(*args, **kwargs)
        bound.apply_defaults()
    except TypeError as e:
        # Mismatched arguments passed to the function, let the original call fail later
        logger.warning(
            "Argument binding failed for %s: %s. Caching might be skipped.", fqn, e
        )
        # Create a pseudo-key to ensure cache miss, or re-raise?
        # Let's create a non-colliding key indicating failure.
        return f"invalid_args:{fqn}:{time.time()}"  # Ensures miss

    arguments_for_key = bound.arguments.copy()
    # Exclude specified parameters from the key
    if exclude_params:
        for p in exclude_params:
            if p in arguments_for_key:
                # Remove or replace with a constant placeholder
                del arguments_for_key[p]
                # arguments_for_key[p] = "__EXCLUDED__" # Alternative

    # Pickle arguments for stability (handles complex types) and hash
    # Use protocol 4 for better compatibility and efficiency
    try:
        # Sort dict to ensure consistent order for hashing
        sorted_args = dict(sorted(arguments_for_key.items()))
        raw_key_data = (fqn, sorted_args)  # Tuple ensures order matters
        pickled_key_data = pickle.dumps(raw_key_data, protocol=4)
        key_hash = md5(pickled_key_data).hexdigest()
        return key_hash
    except Exception as e:
        logger.error(
            "Failed to generate cache key for %s due to pickling error: %s",
            fqn,
            e,
            exc_info=True,
        )
        raise  # Propagate pickling error for key generation


###############################################################################
# The Decorator
###############################################################################
def cache(
    path: str = ".cache.db",
    ttl: float = None,
    max_fqn_capacity: int = None,
    max_age: float = None,
    exclude_params=None,
    ttl_policy_func=None,
):
    """
    Decorator to cache function results in a local SQLite DB. Handles both sync and async functions.

    Args:
        path (str): Path to the SQLite database file. Defaults to ".cache.db".
        ttl (float, optional): Time-to-live in seconds. If set, cached items older than
            this are considered stale on retrieval and ignored/deleted. Defaults to None.
        max_fqn_capacity (int, optional): If set, limits the number of cached items for
            this specific function (FQN). Oldest items are evicted when capacity is exceeded.
            Defaults to None.
        max_age (float, optional): If set, forcibly removes items *for this specific function (FQN)*
            older than `max_age` seconds upon each cache insertion. Defaults to None.
        exclude_params (list[str], optional): A list of parameter names to exclude from
            the cache key generation. Useful for volatile or irrelevant arguments. Defaults to None.
    """
    exclude_params_set = set(exclude_params or [])

    if ttl_policy_func is not None and not callable(ttl_policy_func):
        raise TypeError("ttl_policy_func must be a callable or None")

    def decorator(fn):
        fqn = _get_fqn(fn)
        func_sig = inspect.signature(fn)
        is_async = inspect.iscoroutinefunction(fn)
        # Get the shared Cashier instance for the specified path
        # Errors during instance creation will propagate here
        try:
            cashier = get_cashier_instance(path=path)
        except Exception as e:
            logger.critical(
                "Failed to obtain Cashier instance for %s used by %s. Caching disabled for this function.",
                path,
                fqn,
                exc_info=True,
            )
            # Return the original function if cache cannot be initialized
            return fn

        @wraps(fn)
        def wrapper(*args, **kwargs):
            # 1. Build the cache key (handles errors by raising)
            try:
                key = _build_cache_key(fqn, func_sig, args, kwargs, exclude_params_set)
            except Exception:
                # Key generation failed (e.g., unpickleable args), call original function
                logger.error(
                    "Skipping cache due to key generation failure for %s",
                    fqn,
                    exc_info=True,
                )
                if is_async:
                    # Need to return awaitable for async function
                    async def passthrough_async():
                        return await fn(*args, **kwargs)

                    return passthrough_async()
                else:
                    return fn(*args, **kwargs)

            # 2. Try to get from cache
            try:
                cached_result = cashier.get(key, default_ttl=ttl)
                if cached_result is not None:
                    logger.debug("Cache hit for key=%s (fqn=%s)", key, fqn)
                    if is_async:
                        # If original function was async, return an awaitable
                        # even on cache hit, resolving immediately with the cached value.
                        async def _async_return_cached():
                            return cached_result

                        return _async_return_cached()
                    else:
                        # Original function was sync, return raw value directly
                        return cached_result
            except Exception as e:
                # Error during cache get (DB error, unpickling error)
                logger.error(
                    "Cache get failed for key=%s (fqn=%s): %s. Calling function.",
                    key,
                    fqn,
                    e,
                    exc_info=True,
                )
                # Fall through to calling the function

            # 3. Cache miss or cache read error: Call the function
            logger.debug(
                "Cache miss or error for key=%s (fqn=%s). Calling function...", key, fqn
            )

            # --- Define inner function to handle execution and caching ---
            # This avoids duplicating the policy logic for sync/async paths
            def _execute_and_cache(result):
                cache_directive = (
                    None  # Default: use decorator ttl (via None passed to set)
                )
                specific_ttl_to_set = None

                if ttl_policy_func:
                    try:
                        # Get directive (TTL number, None, or NO_CACHE)
                        cache_directive = ttl_policy_func(result)
                    except Exception as policy_exc:
                        logger.warning(
                            "ttl_policy_func execution failed for fqn=%s: %s. Defaulting to standard TTL.",
                            fqn,
                            policy_exc,
                            exc_info=True,
                        )
                        cache_directive = None  # Default on policy error

                if cache_directive is NO_CACHE:
                    logger.debug(
                        "Skipping cache set based on ttl_policy_func result (NO_CACHE) for key=%s",
                        key,
                    )
                    # Do not cache
                else:
                    # Directive is None or a TTL number
                    specific_ttl_to_set = (
                        cache_directive  # Pass None or the number to set
                    )
                    try:
                        pickled_result = pickle.dumps(result, protocol=4)
                        # Call set, passing the specific TTL derived from the policy
                        cashier.set(
                            key=key,
                            fqn=fqn,
                            val=pickled_result,
                            max_age=max_age,
                            max_fqn_capacity=max_fqn_capacity,
                            specific_ttl=specific_ttl_to_set,  # Pass policy result here
                        )
                        logger.debug(
                            "Stored result in cache for key=%s (fqn=%s, specific_ttl=%s)",
                            key,
                            fqn,
                            specific_ttl_to_set,
                        )
                    except Exception as cache_set_exc:
                        logger.error(
                            "Failed to cache result for key=%s (fqn=%s): %s",
                            key,
                            fqn,
                            cache_set_exc,
                            exc_info=True,
                        )
                        raise cache_set_exc  # Propagate caching error

            if not is_async:
                # --- Handle Synchronous Function ---
                try:
                    result = fn(*args, **kwargs)  # Execute sync function
                except Exception as e:
                    logger.error(
                        "Original sync function execution failed for key=%s (fqn=%s): %s",
                        key,
                        fqn,
                        e,
                    )
                    raise  # Propagate function error

                _execute_and_cache(result)  # Handle caching based on policy
                return result
            else:
                # --- Handle Asynchronous Function ---
                # We cannot await here. Return a new coroutine that does the work.
                async def async_executor():
                    try:
                        # Await the original async function
                        result = await fn(*args, **kwargs)
                    except Exception as e:
                        logger.error(
                            "Original async function execution failed for key=%s (fqn=%s): %s",
                            key,
                            fqn,
                            e,
                        )
                        raise  # Propagate function error

                    # Run the caching logic (including policy) in executor
                    # Note: _execute_and_cache itself doesn't need to be async
                    #       because cashier.set is thread-safe (locked).
                    #       We run it in executor primarily because pickle.dumps might block.
                    loop = asyncio.get_running_loop()
                    try:
                        await loop.run_in_executor(None, _execute_and_cache, result)
                    except Exception as cache_exec_exc:
                        # Error occurred during pickling or cashier.set via executor
                        # _execute_and_cache already logs and raises, executor propagates
                        raise cache_exec_exc

                    return result  # Return original awaited result

                return async_executor()  # Return the coroutine to the caller

        def clear_cache_for_this_fn():
            """Clears all cache entries associated with this specific function."""
            logger.debug("Clearing cache for function %s (path=%s)", fqn, path)
            try:
                # Need to get the correct cashier instance
                instance = get_cashier_instance(path=path)
                instance.delete_by_fqn(fqn)
            except Exception as e:
                logger.error(
                    "Failed to clear cache for fqn=%s (path=%s): %s",
                    fqn,
                    path,
                    e,
                    exc_info=True,
                )
                # Optionally re-raise

        def close_cache_for_this_fn():
            """
            Closes the database connection associated with this function's cache path.
            Note: This closes the connection for ALL functions sharing this cache path.
            """
            logger.warning(
                "Closing cache connection for path %s (used by %s and potentially others).",
                path,
                fqn,
            )
            try:
                instance = get_cashier_instance(path=path)
                instance.close()  # This handles unregistering etc.
            except Exception as e:
                logger.error(
                    "Failed to close cache for path=%s: %s", path, e, exc_info=True
                )
                # Optionally re-raise

        # Attach helper methods to the wrapped function
        wrapper.clear_cache = clear_cache_for_this_fn
        # Renamed for clarity as it affects the shared path connection:
        wrapper.close_shared_cache = close_cache_for_this_fn
        # Expose FQN and potentially the cashier instance if needed (use with caution)
        wrapper._cache_fqn = fqn
        # wrapper._cashier = cashier # Careful exposing mutable shared state

        return wrapper

    return decorator
