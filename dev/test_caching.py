import sys
import os
import time
import pytest
import asyncio
import threading
import sqlite3
import pickle
from unittest.mock import patch

# Add the directory containing your cache module to the Python path
# Adjust this path if your cache module is located elsewhere
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the components to be tested
# Assuming your caching code is in 'my_cache_module.py'
try:
    from caching import (
        Cashier,
        cache,
        NO_CACHE,
        _global_cashier_registry,
        _registry_lock,
        _cleanup_registered,
        get_cashier_instance,
        _cleanup_all_cashiers,
    )
except ImportError:
    pytest.skip("Cache module not found. Skipping tests.", allow_module_level=True)

# --- Fixtures ---


@pytest.fixture(autouse=True)
def clean_global_state():
    """Ensures global registry and flags are reset between tests."""
    global _global_cashier_registry, _cleanup_registered
    # Close any existing connections before clearing
    _cleanup_all_cashiers()  # Call cleanup to close open connections
    with _registry_lock:
        _global_cashier_registry.clear()
    _cleanup_registered = False
    # Ensure atexit doesn't hold onto the old cleanup function if tests re-register
    import atexit

    try:
        atexit.unregister(_cleanup_all_cashiers)
    except ValueError:  # Already unregistered or never registered
        pass
    yield  # Run the test
    # Cleanup after test run as well
    _cleanup_all_cashiers()
    with _registry_lock:
        _global_cashier_registry.clear()
    _cleanup_registered = False
    try:
        atexit.unregister(_cleanup_all_cashiers)
    except ValueError:
        pass


@pytest.fixture
def cache_path(tmp_path):
    """Provides a temporary path for the cache DB file."""
    return tmp_path / "test_cache.db"


# --- Test Data and Helpers ---


class NonPickleable:
    def __getstate__(self):
        raise TypeError("This object cannot be pickled")


execution_flags = {}  # Track function executions


def reset_flags():
    global execution_flags
    execution_flags.clear()


def sync_func(x, y=10):
    """Simple synchronous function to test caching."""
    flag_name = f"sync_func_{x}_{y}"
    execution_flags[flag_name] = execution_flags.get(flag_name, 0) + 1
    return x + y


async def async_func(x, y=20):
    """Simple asynchronous function to test caching."""
    flag_name = f"async_func_{x}_{y}"
    execution_flags[flag_name] = execution_flags.get(flag_name, 0) + 1
    await asyncio.sleep(0.01)  # Simulate async work
    return x * y


def error_func(x):
    """Function that raises an error."""
    raise ValueError("Test error from function")


def unpickleable_return_func(x):
    """Function that returns a non-pickleable object."""
    return NonPickleable()


async def async_unpickleable_return_func(x):
    """Async function that returns a non-pickleable object."""
    await asyncio.sleep(0.01)
    return NonPickleable()


# --- Cashier Class Tests ---


class TestCashier:

    def test_init_create_file(self, cache_path):
        assert not os.path.exists(cache_path)
        cashier = Cashier(path=str(cache_path))
        assert os.path.exists(cache_path)
        cashier.close()

    def test_set_get_basic(self, cache_path):
        cashier = Cashier(str(cache_path))
        key = "test_key_1"
        fqn = "test.fqn"
        value = {"a": 1, "b": "hello"}
        pickled_value = pickle.dumps(value, protocol=4)

        assert cashier.get(key) is None  # Cache miss
        cashier.set(key, fqn, pickled_value)
        retrieved = cashier.get(key)
        assert retrieved == value  # Cache hit
        cashier.close()

    def test_get_ttl_expired(self, cache_path):
        cashier = Cashier(str(cache_path))
        key = "ttl_key"
        fqn = "test.fqn"
        value = "data"
        pickled_value = pickle.dumps(value, protocol=4)
        ttl = 0.1  # seconds

        cashier.set(key, fqn, pickled_value)
        time.sleep(ttl + 0.05)  # Wait longer than TTL
        assert cashier.get(key, default_ttl=ttl) is None  # Should be expired
        # Verify it was deleted
        assert cashier.get(key) is None
        cashier.close()

    def test_get_ttl_not_expired(self, cache_path):
        cashier = Cashier(str(cache_path))
        key = "ttl_key_valid"
        fqn = "test.fqn"
        value = "data"
        pickled_value = pickle.dumps(value, protocol=4)
        ttl = 0.2

        cashier.set(key, fqn, pickled_value)
        time.sleep(0.05)  # Wait less than TTL
        assert cashier.get(key, default_ttl=ttl) == value  # Should still be valid
        cashier.close()

    def test_delete_by_key(self, cache_path):
        cashier = Cashier(str(cache_path))
        key = "del_key"
        fqn = "test.fqn"
        value = "to_delete"
        pickled_value = pickle.dumps(value, protocol=4)

        cashier.set(key, fqn, pickled_value)
        assert cashier.get(key) == value  # Verify set
        cashier.delete_by_key(key)
        assert cashier.get(key) is None  # Verify deleted
        cashier.close()

    def test_delete_by_fqn(self, cache_path):
        cashier = Cashier(str(cache_path))
        fqn1 = "func.one"
        fqn2 = "func.two"
        keys_fqn1 = ["k1_f1", "k2_f1"]
        keys_fqn2 = ["k1_f2"]
        pickled_val = pickle.dumps("data", protocol=4)

        for k in keys_fqn1:
            cashier.set(k, fqn1, pickled_val)
        for k in keys_fqn2:
            cashier.set(k, fqn2, pickled_val)

        # Verify all set
        assert cashier.get(keys_fqn1[0]) == "data"
        assert cashier.get(keys_fqn1[1]) == "data"
        assert cashier.get(keys_fqn2[0]) == "data"

        cashier.delete_by_fqn(fqn1)

        # Verify only fqn1 deleted
        assert cashier.get(keys_fqn1[0]) is None
        assert cashier.get(keys_fqn1[1]) is None
        assert cashier.get(keys_fqn2[0]) == "data"  # fqn2 should remain
        cashier.close()

    def test_max_fqn_capacity(self, cache_path):
        cashier = Cashier(str(cache_path))
        fqn = "capacity.test"
        capacity = 3
        pickled_val = pickle.dumps(0, protocol=4)  # Value doesn't matter here

        # Insert 5 items
        keys = []
        for i in range(5):
            key = f"cap_key_{i}"
            keys.append(key)
            # Pass capacity limit on each set
            cashier.set(key, fqn, pickled_val, max_fqn_capacity=capacity)
            time.sleep(0.01)  # Ensure distinct insert times

        # Check count (using direct SQL for verification)
        with cashier._lock, cashier._conn:
            count = cashier._conn.execute(
                "SELECT COUNT(*) FROM bucket WHERE fqn = ?", (fqn,)
            ).fetchone()[0]
            assert count == capacity

        # Verify only the *last* 'capacity' items remain
        assert cashier.get(keys[0]) is None  # Oldest, should be evicted
        assert cashier.get(keys[1]) is None  # Second oldest, should be evicted
        assert cashier.get(keys[2]) is not None  # Should remain
        assert cashier.get(keys[3]) is not None  # Should remain
        assert cashier.get(keys[4]) is not None  # Newest, should remain
        cashier.close()

    def test_max_age_scoped_fqn(self, cache_path):
        cashier = Cashier(str(cache_path))
        fqn1 = "maxage.one"
        fqn2 = "maxage.two"
        max_age_sec = 0.1
        pickled_val = pickle.dumps("v", protocol=4)

        # Set items for both FQNs
        cashier.set("k1_f1_old", fqn1, pickled_val)
        cashier.set("k1_f2_old", fqn2, pickled_val)
        time.sleep(max_age_sec + 0.05)  # Wait longer than max_age

        # Set a new item for FQN1, triggering its max_age cleanup
        cashier.set("k2_f1_new", fqn1, pickled_val, max_age=max_age_sec)

        # Verify FQN1's old item is gone, new one exists
        assert cashier.get("k1_f1_old") is None
        assert cashier.get("k2_f1_new") == "v"

        # Verify FQN2's old item *still exists* because cleanup was scoped
        assert cashier.get("k1_f2_old") == "v"
        cashier.close()

    def test_close_and_reopen(self, cache_path):
        cashier1 = get_cashier_instance(str(cache_path))
        key = "persist_key"
        cashier1.set(key, "test.fqn", pickle.dumps("persisted", protocol=4))
        assert cashier1.get(key) == "persisted"

        # Close the connection via the instance
        cashier1.close()

        # Verify operating after close raises error (optional, depends on exact behavior desired)
        with pytest.raises(sqlite3.Error):
            cashier1.get(key)  # Operation should fail on closed connection

        # Get instance again - should create a new connection to the same file
        cashier2 = get_cashier_instance(str(cache_path))
        assert cashier2 is not cashier1  # Should be a new object if first was closed
        assert cashier2.get(key) == "persisted"  # Data should persist in the file
        cashier2.close()


# --- Decorator Tests (@cache) ---


class TestCacheDecorator:

    @pytest.fixture(autouse=True)
    def setup_method(self):
        reset_flags()  # Reset execution counter before each test

    def test_sync_basic_hit_miss(self, cache_path):
        cached_sync_func = cache(path=str(cache_path))(sync_func)

        # First call - miss
        assert cached_sync_func(5) == 15
        assert execution_flags.get("sync_func_5_10", 0) == 1

        # Second call - hit
        assert cached_sync_func(5) == 15
        assert execution_flags.get("sync_func_5_10", 0) == 1  # Should not increment

        # Call with different args - miss
        assert cached_sync_func(6) == 16
        assert execution_flags.get("sync_func_6_10", 0) == 1

        # Call with different kwargs - miss
        assert cached_sync_func(5, y=11) == 16
        assert execution_flags.get("sync_func_5_11", 0) == 1

        # Call again - hit
        assert cached_sync_func(5, y=11) == 16
        assert execution_flags.get("sync_func_5_11", 0) == 1

    @pytest.mark.asyncio
    async def test_async_basic_hit_miss(self, cache_path):
        cached_async_func = cache(path=str(cache_path))(async_func)

        # First call - miss
        assert await cached_async_func(5) == 100
        assert execution_flags.get("async_func_5_20", 0) == 1

        # Second call - hit
        assert await cached_async_func(5) == 100
        assert execution_flags.get("async_func_5_20", 0) == 1

        # Call with different args - miss
        assert await cached_async_func(6) == 120
        assert execution_flags.get("async_func_6_20", 0) == 1

        # Call with different kwargs - miss
        assert await cached_async_func(5, y=30) == 150
        assert execution_flags.get("async_func_5_30", 0) == 1

        # Call again - hit
        assert await cached_async_func(5, y=30) == 150
        assert execution_flags.get("async_func_5_30", 0) == 1

    def test_sync_ttl(self, cache_path):
        ttl_sec = 0.1
        cached_sync_func = cache(path=str(cache_path), ttl=ttl_sec)(sync_func)

        # Call 1 (miss)
        assert cached_sync_func(1) == 11
        assert execution_flags.get("sync_func_1_10", 0) == 1
        # Call 2 (hit - within TTL)
        time.sleep(0.05)
        assert cached_sync_func(1) == 11
        assert execution_flags.get("sync_func_1_10", 0) == 1
        # Call 3 (miss - after TTL)
        time.sleep(ttl_sec)
        assert cached_sync_func(1) == 11
        assert execution_flags.get("sync_func_1_10", 0) == 2  # Executed again

    @pytest.mark.asyncio
    async def test_async_ttl(self, cache_path):
        ttl_sec = 0.1
        cached_async_func = cache(path=str(cache_path), ttl=ttl_sec)(async_func)

        # Call 1 (miss)
        assert await cached_async_func(2) == 40
        assert execution_flags.get("async_func_2_20", 0) == 1
        # Call 2 (hit - within TTL)
        await asyncio.sleep(0.05)
        assert await cached_async_func(2) == 40
        assert execution_flags.get("async_func_2_20", 0) == 1
        # Call 3 (miss - after TTL)
        await asyncio.sleep(ttl_sec)
        assert await cached_async_func(2) == 40
        assert execution_flags.get("async_func_2_20", 0) == 2  # Executed again

    def test_exclude_params(self, cache_path):
        cached_sync_func = cache(path=str(cache_path), exclude_params=["y"])(sync_func)

        # Call 1 (miss)
        assert cached_sync_func(5, y=100) == 105  # y=100 used in execution
        assert execution_flags.get("sync_func_5_100", 0) == 1

        # Call 2 (hit, y changed but excluded)
        assert (
            cached_sync_func(5, y=200) == 105
        )  # y=200 passed, but cache key ignores it, returns 105
        assert execution_flags.get("sync_func_5_100", 0) == 1  # No new execution flag
        assert (
            execution_flags.get("sync_func_5_200", 0) == 0
        )  # Function with y=200 was NOT executed

        # Call 3 (miss, x changed)
        assert cached_sync_func(6, y=100) == 106
        assert execution_flags.get("sync_func_6_100", 0) == 1

    def test_clear_cache_helper(self, cache_path):
        cached_sync_func = cache(path=str(cache_path))(sync_func)

        # Call 1 (miss)
        assert cached_sync_func(7) == 17
        assert execution_flags.get("sync_func_7_10", 0) == 1
        # Call 2 (hit)
        assert cached_sync_func(7) == 17
        assert execution_flags.get("sync_func_7_10", 0) == 1

        # Clear cache for this function
        cached_sync_func.clear_cache()

        # Call 3 (miss again)
        assert cached_sync_func(7) == 17
        assert execution_flags.get("sync_func_7_10", 0) == 2

    def test_sync_error_propagation(self, cache_path):
        cached_error_func = cache(path=str(cache_path))(error_func)
        with pytest.raises(ValueError, match="Test error from function"):
            cached_error_func(1)

    @pytest.mark.asyncio
    async def test_async_error_propagation(self, cache_path):
        # Need separate async error func
        @cache(path=str(cache_path))
        async def async_error_func(x):
            await asyncio.sleep(0.01)
            raise ValueError("Async test error")

        with pytest.raises(ValueError, match="Async test error"):
            await async_error_func(1)

    def test_sync_unpickleable_return(self, cache_path):
        cached_unpickleable_func = cache(path=str(cache_path))(unpickleable_return_func)

        # First call executes the function, but fails during pickling/caching
        with pytest.raises(TypeError, match="cannot be pickled"):
            cached_unpickleable_func(1)

        # Second call should re-execute and fail again (not cached)
        with pytest.raises(TypeError, match="cannot be pickled"):
            cached_unpickleable_func(1)

    @pytest.mark.asyncio
    async def test_async_unpickleable_return(self, cache_path):
        cached_async_unpickleable = cache(path=str(cache_path))(
            async_unpickleable_return_func
        )

        # First call executes, fails during pickling/caching within run_in_executor
        # The error from run_in_executor should be propagated
        with pytest.raises(TypeError, match="cannot be pickled"):
            await cached_async_unpickleable(1)

        # Second call should re-execute and fail again
        with pytest.raises(TypeError, match="cannot be pickled"):
            await cached_async_unpickleable(1)

    def test_multiple_functions_same_cache(self, cache_path):
        cached_sync1 = cache(path=str(cache_path))(sync_func)
        cached_sync2 = cache(path=str(cache_path))(lambda x: x * 2)  # Different func

        # Cache func1
        assert cached_sync1(10) == 20
        assert execution_flags.get("sync_func_10_10", 0) == 1
        assert cached_sync1(10) == 20
        assert execution_flags.get("sync_func_10_10", 0) == 1

        # Cache func2 - should not interfere
        assert cached_sync2(10) == 20
        assert cached_sync2(10) == 20

        # Verify func1 cache still works
        assert cached_sync1(10) == 20
        assert execution_flags.get("sync_func_10_10", 0) == 1

        # Clear func1's cache, func2 should be unaffected
        cached_sync1.clear_cache()
        assert cached_sync1(10) == 20  # Re-executes
        assert execution_flags.get("sync_func_10_10", 0) == 2
        assert cached_sync2(10) == 20  # Still cached

    # Add tests similar to Cashier tests for max_age and max_fqn_capacity,
    # but calling the decorated function instead of cashier.set directly.
    def test_decorator_max_fqn_capacity(self, cache_path):
        capacity = 2

        @cache(path=str(cache_path), max_fqn_capacity=capacity)
        def capacity_test_func(i):
            flag_name = f"cap_func_{i}"
            execution_flags[flag_name] = execution_flags.get(flag_name, 0) + 1
            return i * 10

        results = {}
        for i in range(4):  # Call 4 times
            results[i] = capacity_test_func(i)
            time.sleep(0.01)

        # Check execution counts
        assert execution_flags.get("cap_func_0", 0) == 1
        assert execution_flags.get("cap_func_1", 0) == 1
        assert execution_flags.get("cap_func_2", 0) == 1
        assert execution_flags.get("cap_func_3", 0) == 1

        # Try calling again - check which are hits/misses
        reset_flags()
        results_after = {}
        results_after[0] = capacity_test_func(0)  # Should be miss (evicted)
        results_after[1] = capacity_test_func(1)  # Should be miss (evicted)
        results_after[2] = capacity_test_func(2)  # Should be hit
        results_after[3] = capacity_test_func(3)  # Should be hit

        # Verify the execution flags *after* all calls in the second round.
        # Due to the capacity limit and the order of calls, every call in the
        # second round resulted in a cache miss and re-execution.
        assert execution_flags.get("cap_func_0", 0) == 1  # Was executed in 2nd round
        assert execution_flags.get("cap_func_1", 0) == 1  # Was executed in 2nd round
        assert execution_flags.get("cap_func_2", 0) == 1  # Was executed in 2nd round
        assert execution_flags.get("cap_func_3", 0) == 1  # Was executed in 2nd round

    def test_decorator_max_age(self, cache_path):
        max_age_sec = 0.1

        @cache(path=str(cache_path), max_age=max_age_sec)
        def age_test_func(i):
            flag_name = f"age_func_{i}"
            execution_flags[flag_name] = execution_flags.get(flag_name, 0) + 1
            return i * 100

        # Call 1 (miss)
        assert age_test_func(1) == 100
        assert execution_flags.get("age_func_1", 0) == 1
        # Wait longer than max_age
        time.sleep(max_age_sec + 0.05)

        # Call 2 (miss, different arg, triggers cleanup for func)
        assert age_test_func(2) == 200
        assert execution_flags.get("age_func_2", 0) == 1

        # Call 1 again (should be miss, was cleaned up by call 2's set)
        assert age_test_func(1) == 100
        assert execution_flags.get("age_func_1", 0) == 2  # Re-executed

    def test_ttl_policy_sync_variable_ttl(self, cache_path):
        short_ttl = 0.1
        long_ttl = 0.3

        def variable_ttl_policy(result):
            if result == "error":
                return short_ttl
            elif result == "ok":
                return long_ttl
            else:
                return None  # Use decorator default (if any)

        @cache(path=str(cache_path), ttl=60, ttl_policy_func=variable_ttl_policy)
        def func_varying_ttl(key):
            flag_name = f"vary_ttl_{key}"
            execution_flags[flag_name] = execution_flags.get(flag_name, 0) + 1
            return key  # Return the input string directly

        # Test short TTL
        assert func_varying_ttl("error") == "error"  # Miss
        assert execution_flags.get("vary_ttl_error", 0) == 1
        assert func_varying_ttl("error") == "error"  # Hit
        assert execution_flags.get("vary_ttl_error", 0) == 1
        time.sleep(short_ttl + 0.05)
        assert func_varying_ttl("error") == "error"  # Miss again (short TTL expired)
        assert execution_flags.get("vary_ttl_error", 0) == 2

        reset_flags()

        # Test long TTL
        assert func_varying_ttl("ok") == "ok"  # Miss
        assert execution_flags.get("vary_ttl_ok", 0) == 1
        assert func_varying_ttl("ok") == "ok"  # Hit
        assert execution_flags.get("vary_ttl_ok", 0) == 1
        time.sleep(short_ttl + 0.05)  # Wait *longer* than short TTL
        assert func_varying_ttl("ok") == "ok"  # Still Hit (long TTL active)
        assert execution_flags.get("vary_ttl_ok", 0) == 1
        time.sleep(long_ttl - short_ttl + 0.05)  # Wait for long TTL total
        assert func_varying_ttl("ok") == "ok"  # Miss again (long TTL expired)
        assert execution_flags.get("vary_ttl_ok", 0) == 2

    @pytest.mark.asyncio
    async def test_ttl_policy_async_variable_ttl(self, cache_path):
        short_ttl = 0.1
        long_ttl = 0.3

        def variable_ttl_policy(result):
            return short_ttl if result == "error" else long_ttl

        @cache(path=str(cache_path), ttl_policy_func=variable_ttl_policy)
        async def async_func_varying_ttl(key):
            flag_name = f"async_vary_{key}"
            execution_flags[flag_name] = execution_flags.get(flag_name, 0) + 1
            await asyncio.sleep(0.01)
            return key

        # Test short TTL
        assert await async_func_varying_ttl("error") == "error"  # Miss
        assert execution_flags.get("async_vary_error", 0) == 1
        assert await async_func_varying_ttl("error") == "error"  # Hit
        assert execution_flags.get("async_vary_error", 0) == 1
        await asyncio.sleep(short_ttl + 0.05)
        assert await async_func_varying_ttl("error") == "error"  # Miss
        assert execution_flags.get("async_vary_error", 0) == 2

        reset_flags()

        # Test long TTL
        assert await async_func_varying_ttl("ok") == "ok"  # Miss
        assert execution_flags.get("async_vary_ok", 0) == 1
        assert await async_func_varying_ttl("ok") == "ok"  # Hit
        assert execution_flags.get("async_vary_ok", 0) == 1
        await asyncio.sleep(short_ttl + 0.05)
        assert await async_func_varying_ttl("ok") == "ok"  # Hit
        assert execution_flags.get("async_vary_ok", 0) == 1
        await asyncio.sleep(long_ttl - short_ttl + 0.05)
        assert await async_func_varying_ttl("ok") == "ok"  # Miss
        assert execution_flags.get("async_vary_ok", 0) == 2

    def test_ttl_policy_sync_no_cache(self, cache_path):
        def no_cache_policy(result):
            return NO_CACHE if result == "nocache" else None

        @cache(path=str(cache_path), ttl=60, ttl_policy_func=no_cache_policy)
        def func_no_cache(key):
            flag_name = f"no_cache_{key}"
            execution_flags[flag_name] = execution_flags.get(flag_name, 0) + 1
            return key

        # Call with value that should NOT be cached
        assert func_no_cache("nocache") == "nocache"  # Executes
        assert execution_flags.get("no_cache_nocache", 0) == 1
        assert func_no_cache("nocache") == "nocache"  # Executes again (was not cached)
        assert execution_flags.get("no_cache_nocache", 0) == 2

        # Call with value that SHOULD be cached (policy returns None -> default TTL)
        assert func_no_cache("cacheme") == "cacheme"  # Executes
        assert execution_flags.get("no_cache_cacheme", 0) == 1
        assert func_no_cache("cacheme") == "cacheme"  # Cache Hit
        assert execution_flags.get("no_cache_cacheme", 0) == 1

    @pytest.mark.asyncio
    async def test_ttl_policy_async_no_cache(self, cache_path):
        def no_cache_policy(result):
            return NO_CACHE if result == "nocache" else 0.1  # Short TTL otherwise

        @cache(path=str(cache_path), ttl_policy_func=no_cache_policy)
        async def async_func_no_cache(key):
            flag_name = f"async_no_cache_{key}"
            execution_flags[flag_name] = execution_flags.get(flag_name, 0) + 1
            await asyncio.sleep(0.01)
            return key

        # No Cache case
        assert await async_func_no_cache("nocache") == "nocache"
        assert execution_flags.get("async_no_cache_nocache", 0) == 1
        assert await async_func_no_cache("nocache") == "nocache"  # Execute again
        assert execution_flags.get("async_no_cache_nocache", 0) == 2

        # Cache case (short TTL)
        assert await async_func_no_cache("cacheme") == "cacheme"
        assert execution_flags.get("async_no_cache_cacheme", 0) == 1
        assert await async_func_no_cache("cacheme") == "cacheme"  # Hit
        assert execution_flags.get("async_no_cache_cacheme", 0) == 1
        await asyncio.sleep(0.15)
        assert await async_func_no_cache("cacheme") == "cacheme"  # Miss (TTL expired)
        assert execution_flags.get("async_no_cache_cacheme", 0) == 2

    def test_ttl_policy_sync_policy_error(self, cache_path):
        def policy_that_errors(result):
            if result == "bad":
                raise ValueError("Policy error")
            return 10

        # Default TTL = 30s
        @cache(path=str(cache_path), ttl=5, ttl_policy_func=policy_that_errors)
        def func_policy_error(key):
            flag_name = f"policy_err_{key}"
            execution_flags[flag_name] = execution_flags.get(flag_name, 0) + 1
            return key

        # Call where policy works
        assert func_policy_error("good") == "good"  # Miss, policy returns 60s
        assert execution_flags.get("policy_err_good", 0) == 1
        assert func_policy_error("good") == "good"  # Hit
        assert execution_flags.get("policy_err_good", 0) == 1

        # Call where policy fails
        assert func_policy_error("bad") == "bad"  # Miss, policy errors during set
        assert execution_flags.get("policy_err_bad", 0) == 1  # Function executed
        # Call again - should use default TTL (30s) because policy failed on set
        assert func_policy_error("bad") == "bad"  # Hit (using default TTL logic)
        assert execution_flags.get("policy_err_bad", 0) == 1

        # Check expiration based on default TTL
        time.sleep(6)
        assert func_policy_error("bad") == "bad"  # Miss (default TTL expired)
        assert execution_flags.get("policy_err_bad", 0) == 2  # Re-executed


# --- Global State / Factory Tests ---


def test_get_cashier_instance_reuse(cache_path, clean_global_state):
    path_str = str(cache_path)
    instance1 = get_cashier_instance(path_str)
    instance2 = get_cashier_instance(path_str)
    assert instance1 is instance2  # Should return same instance for same path
    instance1.close()


def test_get_cashier_instance_different_paths(tmp_path, clean_global_state):
    path1 = str(tmp_path / "cache1.db")
    path2 = str(tmp_path / "cache2.db")
    instance1 = get_cashier_instance(path1)
    instance2 = get_cashier_instance(path2)
    assert instance1 is not instance2
    assert instance1.path == os.path.abspath(path1)
    assert instance2.path == os.path.abspath(path2)
    instance1.close()
    instance2.close()


# Note: Testing atexit behavior directly is complex in unit tests.
# We rely on the clean_global_state fixture calling _cleanup_all_cashiers
# to ensure connections are closed between tests. Manual inspection or
# integration tests are better for verifying atexit registration itself.
