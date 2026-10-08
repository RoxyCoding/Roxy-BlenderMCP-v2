"""Exercise LOOK's actual settings/cleanup block without Blender or a GPU."""
import textwrap
from types import SimpleNamespace

import pytest

from blender_mcp.blender_scripts import LOOK


def run_capture(mode, shading, *, fail_restore=False):
    scene = SimpleNamespace(frame_current=1, frame_start=1, frame_end=250, camera=None,
                            render=SimpleNamespace(engine="CYCLES"))

    def frame_set(frame):
        if fail_restore and frame == 1:
            raise RuntimeError("frame restore failed")
        scene.frame_current = frame

    scene.frame_set = frame_set
    space = SimpleNamespace(
        shading=SimpleNamespace(type="SOLID", light="STUDIO", color_type="MATERIAL"),
        overlay=SimpleNamespace(show_cursor=True, show_extras=True,
                                show_relationship_lines=True, show_overlays=True,
                                show_wireframes=False, wireframe_threshold=0.5),
    )

    class Bounds:
        def __sub__(self, other):
            return [1, 1, 1]

    def draw(*args):
        raise RuntimeError("draw failed")

    namespace = dict(scene=scene, space=space, mode=mode, max_size=100,
                     ARGS={"shading": shading, "frames": [10, 20]}, targets=[],
                     center=[0, 0, 0], hi=Bounds(), lo=Bounds(),
                     region=SimpleNamespace(width=100, height=100),
                     current_view=lambda: (None, None), draw=draw,
                     direction_of=lambda view: None)
    block = LOOK[LOOK.index("# Settings each mode changes"):LOOK.index("h, w = image.shape[:2]")]
    exec("def capture():\n" + textwrap.indent(block, "    "), namespace)
    return namespace["capture"], scene, space


@pytest.mark.parametrize("mode,shading", [("angles", "rendered"), ("viewport", "wireframe"),
                                         ("frames", "solid")])
def test_settings_restored_after_early_return_or_draw_error(mode, shading):
    capture, scene, space = run_capture(mode, shading)
    if mode == "angles":
        assert "Rendered shading" in capture()["error"]
    else:
        with pytest.raises(RuntimeError, match="draw failed"):
            capture()
    assert scene.frame_current == 1
    assert space.shading.type == "SOLID"
    assert space.shading.light == "STUDIO"
    assert space.overlay.show_cursor is True
    assert space.overlay.show_overlays is True
    assert space.overlay.show_wireframes is False


def test_frame_restore_error_does_not_skip_settings_cleanup():
    capture, scene, space = run_capture("frames", "rendered", fail_restore=True)
    # Use an engine that allows rendered offscreen capture.
    scene.render.engine = "BLENDER_EEVEE"
    with pytest.raises(RuntimeError, match="frame restore failed"):
        capture()
    assert space.shading.type == "SOLID"
    assert space.overlay.show_cursor is True
