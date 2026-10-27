# Simpul — installation and quick start

For the maintained public installation guide, see **[Get started](public/GETTING_STARTED.md)**.

Supported source runtime: Python 3.11–3.13, Git, an MCP stdio-compatible client. CI tests Ubuntu and Windows on Python 3.11 and 3.13. Use a virtual environment and the actual venv Python in your MCP client configuration.

To run the server:

```bash
python -m pip install -e .
python -m subagentbridge.server
```

This is an MCP stdio service; it does not open a chat window. `v1.0.0` is the historical published release; use only an actually published version tag for reproducible release installations. Latest source may include beta changes that are not yet released.

Security and required operator boundaries: [public security guide](public/SECURITY.md).
