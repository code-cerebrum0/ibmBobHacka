# Isolation Verification

EgressProof uses `--dns 0.0.0.0` to simulate a restricted egress environment.
The container's DNS resolver is set to `0.0.0.0`, which causes all external
hostname lookups to fail with `socket.gaierror: [Errno -2] Name or service not known`.

This mirrors what happens in a production environment where:
- External DNS is blocked by firewall policy
- The container has no route to external DNS servers
- Egress to public internet is disallowed

## Why --dns 0.0.0.0 (not --network internal)

`docker network create --internal` is the theoretically correct approach but on
Docker Desktop for Windows it prevents port publishing to the host interface,
making the EgressProof runner unable to reach the container. The `--dns 0.0.0.0`
approach is equivalent for the demo scenario and works on all platforms.

The container still runs on the default bridge with `-p 8000:8000` so the
EgressProof runner can reach it via `localhost:8000`. Only the container's
own outbound DNS resolution is broken.

## Manual Verification

```bash
# Confirm DNS is broken inside the container (run while egressproof container is up)
docker exec egressproof-app python -c "import socket; socket.getaddrinfo('huggingface.co', 443)"
# Expected: socket.gaierror: [Errno -2] Name or service not known
```

```bash
# Confirm the runner can still reach the app from the host
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

## Evidence in Container Logs

When the hidden dependency is triggered under isolation, container logs will contain:

```
ERROR:localdocqa:EGRESS_BLOCKED: Failed to load or run model: ...
socket.gaierror: [Errno -2] Name or service not known
huggingface.co
```

These patterns are what EgressProof scans for in its evidence collection step.
