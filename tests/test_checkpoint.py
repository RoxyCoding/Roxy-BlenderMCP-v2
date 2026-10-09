"""checkpoint: save / list / restore through the addon's checkpoint commands."""

import asyncio

import pytest

from blender_mcp import server


class FakeBlender:
    def __init__(self, replies):
        # command -> reply, or a list of replies consumed in order
        self.replies = replies
        self.sent = []

    def send_command(self, command, params=None, read_only=False):
        self.sent.append((command, params))
        reply = self.replies[command]
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def connect(monkeypatch):
    async def no_sleep(_):
        pass

    monkeypatch.setattr(server.asyncio, "sleep", no_sleep)

    def _connect(replies):
        blender = FakeBlender(replies)
        monkeypatch.setattr(server, "get_blender_connection", lambda: blender)
        return blender

    return _connect


def _run(**kw):
    return asyncio.run(server.checkpoint(None, **kw))


def test_save_reports_the_id_to_restore(connect):
    blender = connect({"save_checkpoint": {"id": "20261008-120000-abcd", "objects": 12, "size_mb": 1.5, "pruned": []}})
    out = _run(action="save", label="blockout done")
    assert blender.sent == [("save_checkpoint", {"label": "blockout done"})]
    assert 'checkpoint(action="restore", id="20261008-120000-abcd")' in out


def test_list_shows_newest_first_and_other_files(connect):
    connect({"list_checkpoints": {"checkpoints": [
        {"id": "b", "created": "2026-10-08 12:01:00", "objects": 3, "label": "lit", "this_file": True},
        {"id": "a", "created": "2026-10-08 12:00:00", "objects": 2, "this_file": False, "source_file": "C:/x.blend"},
    ]}})
    out = _run(action="list")
    assert out.index("b  ") < out.index("a  ")
    assert '"lit"' in out and "(from C:/x.blend)" in out


def test_restore_waits_until_the_addon_has_reloaded(connect):
    blender = connect({
        "restore_checkpoint": {"scheduled": True, "id": "a", "before_restore": "z", "file": "C:/scene.blend"},
        "list_checkpoints": [
            ConnectionError("Blender is loading"),
            {"last_restore": {"id": "a", "state": "pending"}},
            {"last_restore": {"id": "a", "state": "done", "file": "C:/scene.blend"}},
        ],
    })
    out = _run(action="restore", id="a")
    assert out.startswith("Restored checkpoint a.") and "checkpoint z" in out
    assert [c for c, _ in blender.sent].count("list_checkpoints") == 3


def test_restore_of_an_unsaved_file_asks_for_save_as(connect):
    connect({
        "restore_checkpoint": {"scheduled": True, "id": "a", "before_restore": "z", "file": None},
        "list_checkpoints": {"last_restore": {"id": "a", "state": "done", "file": "C:/restored/restored-a.blend"}},
    })
    assert "Save As" in _run(action="restore", id="a")


def test_restore_errors_are_relayed(connect):
    connect({"restore_checkpoint": {"error": "No checkpoint 'x'. List them to see which there are."}})
    assert _run(action="restore", id="x").startswith("Error: No checkpoint")
    connect({
        "restore_checkpoint": {"scheduled": True, "id": "a", "before_restore": "z", "file": "C:/s.blend"},
        "list_checkpoints": {"last_restore": {"id": "a", "state": "error", "error": "file is corrupt"}},
    })
    assert _run(action="restore", id="a") == "Error restoring a: file is corrupt"


def test_bad_requests_never_reach_blender(connect):
    blender = connect({})
    assert _run(action="undo").startswith("Error: action must be")
    assert _run(action="restore").startswith("Error: restore needs id")
    assert blender.sent == []


def test_old_addon_is_told_to_update(connect, monkeypatch):
    connect({"save_checkpoint": Exception("Unknown command type: save_checkpoint")})
    monkeypatch.setattr(server, "_addon_outdated", lambda: True)
    assert "too old for checkpoints" in _run(action="save")
