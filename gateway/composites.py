"""Dev sample composites — pipelines that orchestrate catalog capabilities.

Like a compose file referencing images from a registry, each composite wires
together capabilities the marketplace already provides.
"""

from __future__ import annotations

from .composer import Composite, Step


def build_dev_composites() -> list[Composite]:
    return [
        Composite(
            name="greet-report",
            description="Greet someone, then report stats on the greeting.",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            steps=[
                # Resolved + ranked like any call: picks the best `greet` vendor.
                Step(name="greeting", capability="greet", inputs={"name": "input.name"}),
                Step(
                    name="stats",
                    capability="text_stats",
                    inputs={"text": "greeting.greeting"},
                ),
            ],
            output={
                "greeting": "greeting.greeting",
                "characters": "stats.characters",
                "words": "stats.words",
            },
        ),
    ]
