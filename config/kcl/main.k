# Author Feature resources here, then `kcl run` to emit Kubernetes YAML.
# Schemas in feature.k are in the same package, so no import is needed.

echo: Feature = {
    metadata = {
        name = "echo"
        namespace = "features"
    }
    spec = {
        description = "Echoes its input back — the reference feature."
        image = "ghcr.io/agennext/feature-echo:0.1.0"
        tags = ["example", "utility"]
        inputSchema = '{"type":"object","properties":{"message":{"type":"string"}},"required":["message"]}'
        outputSchema = '{"type":"object","properties":{"echo":{"type":"string"}}}'
        runtime = {
            minReplicas = 1
            maxReplicas = 5
            resources = {
                requests = {cpu = "100m", memory = "128Mi"}
            }
        }
    }
}

# A second, AI-native feature requesting a GPU.
summarizer: Feature = {
    metadata = {
        name = "web-summarizer"
        namespace = "features"
    }
    spec = {
        description = "Fetches a URL and returns an LLM summary."
        image = "ghcr.io/agennext/feature-web-summarizer:0.1.0"
        tags = ["web", "nlp", "ai"]
        inputSchema = '{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}'
        outputSchema = '{"type":"object","properties":{"summary":{"type":"string"}}}'
        runtime = {
            minReplicas = 0
            maxReplicas = 10
            accelerator = "nvidia.com/gpu"
        }
    }
}

# Emit both as a YAML stream.
{result = [echo, summarizer]}
