"""app: Live's application state, views, selection, messages and browser previews."""

from typing import Annotated, Literal

from pydantic import Field

from tonable.server import call, mcp
from tonable.tools import changes, text


@mcp.tool(annotations=changes("Application and views"))
def app(
    action: Annotated[
        Literal[
            "info",
            "select",
            "show_view",
            "hide_view",
            "focus_view",
            "toggle_browse",
            "scroll_view",
            "zoom_view",
            "set_view",
            "show_message",
            "preview",
            "stop_preview",
        ],
        Field(description="What to do; see the tool description."),
    ],
    target: text(
        "For select: t0, rA, m (track), s2 (scene), t0/s2 or t0/a1 (clip), t0/d1 "
        "(device) or t0/d1:Release (parameter)."
    ) = "",
    view: text(
        "For the view actions: Browser, Arranger, Session, Detail, Detail/Clip or "
        "Detail/DeviceChain."
    ) = "",
    direction: text("For scroll_view and zoom_view: up, down, left or right.") = "",
    modifier: text(
        "For scroll_view and zoom_view: true to hold the modifier key."
    ) = "",
    follow_song: text("For set_view: true / false. Empty: unchanged.") = "",
    draw_mode: text("For set_view: Draw mode on or off. Empty: unchanged.") = "",
    message: text("For show_message: the text for Live's status bar.") = "",
    item: text(
        "For preview: a path from find_in_library, or a unique name or file."
    ) = "",
    refresh: text("For preview: true to walk Live's browser again first.") = "",
) -> dict:
    """Live's own interface and state.

    info: Live version, CPU load, open dialogs (read only: Tonable never presses a
    dialog button) and what is selected, as Tonable addresses. select: select a
    track, scene, clip, device or parameter so the user sees it in Live. show_view,
    hide_view, focus_view, toggle_browse, scroll_view, zoom_view: arrange Live's
    windows. set_view: follow_song and draw_mode. show_message: a status-bar message.
    preview and stop_preview: audition a browser item (a sound or preset) without
    loading it. Selection and view changes are not undo steps.
    """
    return call(
        "app",
        {
            "action": action,
            "target": target,
            "view": view,
            "direction": direction,
            "modifier": modifier,
            "follow_song": follow_song,
            "draw_mode": draw_mode,
            "message": message,
            "item": item,
            "refresh": refresh,
        },
        long=action in ("preview",),
    )
