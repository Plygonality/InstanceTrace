# Privacy

Traces are processed on the machine that runs the command. The package does not open a network connection, and `instancetrace doctor` reports telemetry as disabled.

A manifest can still describe a private scene: object names, graph ids, source paths, labels, and evaluated locators. Treat `trace.json` and `trace.npz` as scene data.

`instancetrace redact` writes a new manifest:

- The default pass clears display labels, display paths, locators, and the host platform string.
- `--strict` replaces source, graph, scene, branch, and path strings with stable `redacted:` tokens and drops notes and config. Logical id bytes stay, because they are already digests. Anyone who knows the namespace and the declaration can recompute them.

Redaction is opt-in. Sharing a strict manifest is still a deliberate publication of structure that hashes might not hide from someone who holds the original ids.

The Blender panel writes a report text block and, when asked, an HTML file under a directory you choose or a temporary directory. It does not upload either.
