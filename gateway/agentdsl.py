"""A tiny textual DSL for declaring agents — ``*.agent.next`` files.

A human-friendly surface over a composite pipeline (see ``composer.Composite``):
declare an agent's inputs, the capability steps it runs, and how its outputs are
wired. The same source compiles to a Composite (to publish + run on the gateway)
and to client stubs in JavaScript, Go, and Rust.

Example::

    agent greet-report
    description "Greet someone, then report stats on the greeting."
    input name: string

    step greeting = greet(name: input.name)
    step stats = text_stats(text: greeting.greeting)

    output greeting = greeting.greeting
    output characters = stats.characters

Parsing is line-oriented and never raises to the caller: it returns the
composite (or ``None``) together with a list of line-numbered error strings.
"""

from __future__ import annotations

import re
from typing import Any

from .composer import Composite, Step

_NAME = r"[A-Za-z_][A-Za-z0-9_-]*"
_REF = r"[A-Za-z_][A-Za-z0-9_.-]*"
_ARG_RE = re.compile(rf"({_NAME})\s*:\s*({_REF})")
_TYPES = {
    "string": "string", "str": "string", "text": "string",
    "number": "number", "float": "number",
    "integer": "integer", "int": "integer",
    "bool": "boolean", "boolean": "boolean",
}


def parse(text: str) -> tuple[Composite | None, list[str]]:
    """Parse agent DSL into a Composite, or ``(None, errors)`` on any error."""

    name = ""
    description = ""
    props: dict[str, Any] = {}
    required: list[str] = []
    steps: list[Step] = []
    output: dict[str, str] = {}
    errors: list[str] = []

    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        if line.startswith("agent "):
            name = line[len("agent "):].strip()
            if not re.fullmatch(_NAME, name):
                errors.append(f"line {i}: invalid agent name '{name}'")

        elif line.startswith("description"):
            description = line[len("description"):].strip().strip('"')

        elif line.startswith("input "):
            m = re.fullmatch(rf"input\s+({_NAME})(\??)\s*:\s*({_NAME})", line)
            if not m:
                errors.append(f"line {i}: bad input (want `input <name>: <type>`): '{line}'")
                continue
            field, optional, typ = m.group(1), m.group(2), m.group(3)
            if typ not in _TYPES:
                errors.append(f"line {i}: unknown type '{typ}' (string|number|integer|boolean)")
                continue
            props[field] = {"type": _TYPES[typ]}
            if optional != "?":
                required.append(field)

        elif line.startswith("step "):
            m = re.fullmatch(rf"step\s+({_NAME})\s*=\s*({_NAME})(?:@({_NAME}))?\s*\((.*)\)", line)
            if not m:
                errors.append(f"line {i}: bad step (want `step <name> = <capability>(<k>: <ref>, …)`): '{line}'")
                continue
            sname, capability, vendor, argstr = m.groups()
            inputs = {am.group(1): am.group(2) for am in _ARG_RE.finditer(argstr)}
            steps.append(Step(name=sname, capability=capability, vendor=vendor, inputs=inputs))

        elif line.startswith("output "):
            m = re.fullmatch(rf"output\s+({_NAME})\s*=\s*({_REF})", line)
            if not m:
                errors.append(f"line {i}: bad output (want `output <name> = <ref>`): '{line}'")
                continue
            output[m.group(1)] = m.group(2)

        else:
            errors.append(f"line {i}: unrecognized statement: '{line}'")

    if not name:
        errors.append("missing `agent <name>` declaration")
    if not steps and not errors:
        errors.append("an agent needs at least one `step`")
    if errors:
        return None, errors

    input_schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        input_schema["required"] = required
    composite = Composite(
        name=name, description=description, input_schema=input_schema,
        steps=steps, output=output,
    )
    return composite, []


# --- code generation: one agent, three client stubs ------------------------

def _parts(name: str) -> list[str]:
    return [p for p in re.split(r"[-_]", name) if p]


def _camel(name: str) -> str:
    parts = _parts(name)
    return parts[0].lower() + "".join(w.capitalize() for w in parts[1:]) if parts else name


def _pascal(name: str) -> str:
    return "".join(w.capitalize() for w in _parts(name)) or name


def _snake(name: str) -> str:
    return "_".join(_parts(name)) or name


_GO_TYPES = {"string": "string", "number": "float64", "integer": "int", "boolean": "bool"}
_TS_TYPES = {"string": "string", "number": "number", "integer": "number", "boolean": "boolean"}
_PROTO_TYPES = {"string": "string", "number": "double", "integer": "int64", "boolean": "bool"}

# Supported codegen targets (and friendly aliases).
LANGUAGES = ("js", "ts", "go", "rust", "java", "proto")
_ALIASES = {"javascript": "js", "typescript": "ts", "golang": "go", "rs": "rust", "protobuf": "proto"}


def codegen(composite: Composite, lang: str) -> str:
    """Generate a client stub that invokes ``composite`` through the gateway."""

    lang = _ALIASES.get(lang, lang)
    props: dict[str, Any] = composite.input_schema.get("properties", {})
    subs = {
        "__NAME__": composite.name,
        "__DESC__": composite.description or "(no description)",
        "__CAMEL__": _camel(composite.name),
        "__PASCAL__": _pascal(composite.name),
        "__SNAKE__": _snake(composite.name),
        "__FIELDS__": ", ".join(props.keys()) or "(no inputs)",
        "__OUTS__": ", ".join(composite.output.keys()) or "(none)",
    }

    if lang == "js":
        template = _JS
    elif lang == "ts":
        subs["__TSFIELDS__"] = "; ".join(
            f"{k}: {_TS_TYPES.get(v.get('type'), 'unknown')}" for k, v in props.items()
        ) or "/* no inputs */"
        template = _TS
    elif lang == "go":
        subs["__GOFIELDS__"] = "\n".join(
            f"\t{_pascal(k)} {_GO_TYPES.get(v.get('type'), 'any')} `json:\"{k}\"`"
            for k, v in props.items()
        ) or "\t// (no inputs)"
        template = _GO
    elif lang == "rust":
        subs["__RSFIELDS__"] = ", ".join(
            f"{k}: {v.get('type', 'string')}" for k, v in props.items()
        ) or "(no inputs)"
        template = _RUST
    elif lang == "java":
        template = _JAVA
    elif lang == "proto":
        subs["__PROTOIN__"] = "\n".join(
            f"  {_PROTO_TYPES.get(v.get('type'), 'string')} {k} = {i};"
            for i, (k, v) in enumerate(props.items(), start=1)
        ) or "  // (no inputs)"
        template = _PROTO
    else:
        return f"// unsupported language: {lang}"

    out = template
    for token, value in subs.items():
        out = out.replace(token, value)
    return out


_JS = """// Generated from __NAME__.agent.next — do not edit by hand.
// Agent __NAME__ — __DESC__
export async function __CAMEL__(input, { baseUrl = "http://localhost:8000" } = {}) {
  // input fields: __FIELDS__
  const res = await fetch(`${baseUrl}/composites/__NAME__/invoke`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ input }),
  });
  if (!res.ok) throw new Error(`agent __NAME__ failed: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data.output; // __OUTS__
}
"""

_GO = """// Generated from __NAME__.agent.next — do not edit by hand.
// Agent __NAME__ — __DESC__
package agents

import (
\t"bytes"
\t"encoding/json"
\t"fmt"
\t"net/http"
)

// __PASCAL__Input is the input for the __NAME__ agent.
type __PASCAL__Input struct {
__GOFIELDS__
}

// __PASCAL__ invokes the __NAME__ agent on the gateway at baseURL.
// Returns the agent output (__OUTS__).
func __PASCAL__(baseURL string, in __PASCAL__Input) (map[string]any, error) {
\tbody, err := json.Marshal(map[string]any{"input": in})
\tif err != nil {
\t\treturn nil, err
\t}
\tresp, err := http.Post(baseURL+"/composites/__NAME__/invoke", "application/json", bytes.NewReader(body))
\tif err != nil {
\t\treturn nil, err
\t}
\tdefer resp.Body.Close()
\tvar out struct {
\t\tOutput map[string]any `json:"output"`
\t\tError  string         `json:"error"`
\t}
\tif err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
\t\treturn nil, err
\t}
\tif out.Error != "" {
\t\treturn nil, fmt.Errorf("agent __NAME__: %s", out.Error)
\t}
\treturn out.Output, nil
}
"""

_RUST = """// Generated from __NAME__.agent.next — do not edit by hand.
// Agent __NAME__ — __DESC__
// Requires: reqwest (blocking feature), serde_json.
use serde_json::{json, Value};

/// Invoke the __NAME__ agent on the gateway at `base_url`.
/// Input fields: __RSFIELDS__ — returns the agent output (__OUTS__).
pub fn __SNAKE__(base_url: &str, input: Value) -> Result<Value, Box<dyn std::error::Error>> {
    let client = reqwest::blocking::Client::new();
    let resp: Value = client
        .post(format!("{base_url}/composites/__NAME__/invoke"))
        .json(&json!({ "input": input }))
        .send()?
        .json()?;
    if let Some(err) = resp.get("error").and_then(Value::as_str) {
        return Err(err.into());
    }
    Ok(resp.get("output").cloned().unwrap_or(Value::Null))
}
"""

_TS = """// Generated from __NAME__.agent.next — do not edit by hand.
// Agent __NAME__ — __DESC__
export interface __PASCAL__Input { __TSFIELDS__ }

export async function __CAMEL__(
  input: __PASCAL__Input,
  baseUrl = "http://localhost:8000",
): Promise<Record<string, unknown>> {
  const res = await fetch(`${baseUrl}/composites/__NAME__/invoke`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ input }),
  });
  if (!res.ok) throw new Error(`agent __NAME__ failed: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data.output; // __OUTS__
}
"""

_JAVA = """// Generated from __NAME__.agent.next — do not edit by hand.
// Agent __NAME__ — __DESC__
// Requires: com.fasterxml.jackson.databind (ObjectMapper), Java 11+ (java.net.http).
package agents;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

public final class __PASCAL__ {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    // Invoke the __NAME__ agent on the gateway at baseUrl. Input fields: __FIELDS__
    // Returns the agent output (__OUTS__).
    public static JsonNode invoke(String baseUrl, Map<String, Object> input) throws Exception {
        byte[] body = MAPPER.writeValueAsBytes(Map.of("input", input));
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/composites/__NAME__/invoke"))
                .header("content-type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        HttpResponse<String> resp = HttpClient.newHttpClient()
                .send(req, HttpResponse.BodyHandlers.ofString());
        JsonNode data = MAPPER.readTree(resp.body());
        if (data.hasNonNull("error")) {
            throw new RuntimeException("agent __NAME__: " + data.get("error").asText());
        }
        return data.get("output");
    }
}
"""

_PROTO = """// Generated from __NAME__.agent.next — do not edit by hand.
// Agent __NAME__ — __DESC__
syntax = "proto3";

package agents.__SNAKE__;

import "google/protobuf/struct.proto";

service __PASCAL__ {
  // Invoke the __NAME__ agent.
  rpc Invoke(__PASCAL__Input) returns (__PASCAL__Output);
}

message __PASCAL__Input {
__PROTOIN__
}

message __PASCAL__Output {
  google.protobuf.Struct output = 1;  // __OUTS__
}
"""
