"""Feature composition — composites that orchestrate other features.

A *composite* is a capability whose implementation is a pipeline of steps, each
invoking another capability through the gateway. Data flows step-to-step via a
tiny reference DSL, and every sub-invocation is resolved and ranked exactly like
a direct call — so a composite automatically gets the best provider at each
step, plus the same validation and metrics.

Composites compose recursively (a step may target another composite), keeping
the agent thin: it calls one capability instead of chaining several tools.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


class Step(BaseModel):
    """One pipeline step: invoke ``capability`` with inputs built from context."""

    name: str
    capability: str
    vendor: str | None = None
    version: str | None = None
    # Maps each input field to a reference into the run context, e.g.
    # {"text": "fetch.content"} or {"name": "input.name"}.
    inputs: dict[str, str] = Field(default_factory=dict)


class Composite(BaseModel):
    """A named pipeline exposed as its own capability."""

    name: str
    capability: str = ""
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
    # Maps each output field to a reference into the run context.
    output: dict[str, str] = Field(default_factory=dict)

    def model_post_init(self, _ctx: Any) -> None:
        if not self.capability:
            self.capability = self.name


class CompositeSummary(BaseModel):
    name: str
    capability: str
    description: str
    steps: list[dict[str, str]]


class CompositeResult(BaseModel):
    composite: str
    output: dict[str, Any]
    trace: list[dict[str, Any]]
    # Set (to a safe, plain-data message) when a step or reference failed. The
    # composer never returns exception/stack-trace state here, so this is safe
    # to surface to callers (cf. CodeQL py/stack-trace-exposure).
    error: str | None = None


# A capability invoker: (capability, input, vendor, version) -> (output, error).
# Exactly one of the pair is set; ``error`` is a safe, caller-facing message.
CapabilityInvoke = Callable[
    [str, dict[str, Any], "str | None", "str | None"],
    Awaitable["tuple[dict[str, Any] | None, str | None]"],
]


def _resolve_ref(ref: str, ctx: dict[str, Any]) -> tuple[Any, str | None]:
    """Resolve a dotted reference like ``input.name`` or ``fetch.content``."""

    cur: Any = ctx
    for part in ref.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None, f"unresolved reference: '{ref}'"
    return cur, None


class Composer:
    """Runs composites against an injected capability invoker.

    Failures (bad references, no provider, step errors) are returned as data on
    :class:`CompositeResult.error` together with the partial trace — never
    raised — so the dispatch path stays exception-free.
    """

    def __init__(self, invoke: CapabilityInvoke) -> None:
        self._invoke = invoke

    async def run(
        self, composite: Composite, caller_input: dict[str, Any]
    ) -> CompositeResult:
        ctx: dict[str, Any] = {"input": caller_input}
        trace: list[dict[str, Any]] = []

        def fail(message: str) -> CompositeResult:
            return CompositeResult(
                composite=composite.name, output={}, trace=trace, error=message
            )

        for step in composite.steps:
            step_input: dict[str, Any] = {}
            for k, ref in step.inputs.items():
                val, err = _resolve_ref(ref, ctx)
                if err:
                    return fail(f"step '{step.name}': {err}")
                step_input[k] = val
            output, err = await self._invoke(step.capability, step_input, step.vendor, step.version)
            if err or output is None:
                return fail(f"step '{step.name}': {err or 'no output'}")
            ctx[step.name] = output
            trace.append({"step": step.name, "capability": step.capability, "output": output})

        result: dict[str, Any] = {}
        for k, ref in composite.output.items():
            val, err = _resolve_ref(ref, ctx)
            if err:
                return fail(err)
            result[k] = val
        return CompositeResult(composite=composite.name, output=result, trace=trace)
