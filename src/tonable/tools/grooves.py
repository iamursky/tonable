"""groove: the Set's groove pool."""

from typing import Annotated, Literal

from pydantic import Field

from tonable.server import call, mcp
from tonable.tools import changes, text


@mcp.tool(annotations=changes("Groove pool", idempotent=True))
def groove(
    action: Annotated[
        Literal["list", "update"],
        Field(description="list the pool, or update a groove or the Set's amount."),
    ],
    groove: text(
        "For update: the groove's number from 0 (see list) or exact name."
    ) = "",
    name: text("For update: a new name for the groove.") = "",
    base: text(
        "For update: grid of the groove: 1/4, 1/8, 1/8T, 1/16, 1/16T, 1/32."
    ) = "",
    timing_amount: text("For update: Timing, 0-100.") = "",
    quantization_amount: text("For update: Quantize, 0-100.") = "",
    random_amount: text("For update: Random, 0-100.") = "",
    velocity_amount: text("For update: Velocity, 0-100.") = "",
    groove_amount: text(
        "For update: the Set's global Groove Amount; the answer shows what Live holds."
    ) = "",
) -> dict:
    """Read the groove pool and tune its grooves: grid, timing, quantize, random and
    velocity amounts, and the Set's global groove amount.

    Live's API cannot create or remove grooves, and cannot clear a clip's groove; it
    can only change the grooves already in the pool. Assign a groove to a clip with
    update_clip. Each field gets its own result line with what Live holds afterwards
    (Live ignores some invalid writes, so check "now"). One undo step.
    """
    return call(
        "groove",
        {
            "action": action,
            "groove": groove,
            "name": name,
            "base": base,
            "timing_amount": timing_amount,
            "quantization_amount": quantization_amount,
            "random_amount": random_amount,
            "velocity_amount": velocity_amount,
            "groove_amount": groove_amount,
        },
    )
