from pathlib import Path
import sys
import asyncio


def _publish_module():
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(workspace_root / "python-lang-mu"))

    import dev.tasks.publish as publish_module

    return publish_module


def test_poll_jitpack_build_status_sleeps_on_not_found(monkeypatch) -> None:
    publish_module = _publish_module()
    from dev.jitpack import JitPackNotFoundError

    class DummyAPI:
        async def get_versions(self, group_id: str, artifact_id: str, mode: str):
            raise JitPackNotFoundError("not found")

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    times = iter([0.0, 0.0, 1201.0])

    monkeypatch.setattr(publish_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(publish_module.time, "time", lambda: next(times))

    result = asyncio.run(
        publish_module.poll_jitpack_build_status(
            DummyAPI(), "com.github.example", "sample-artifact", "1.2.3"
        )
    )

    assert result is None
    assert sleep_calls == [3]
