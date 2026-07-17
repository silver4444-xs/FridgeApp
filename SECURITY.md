# Security Policy

## Supported Versions

Only the latest version on the `main` branch is currently supported with
security updates.

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| < main  | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability within
FridgeAI, please **do not** open a public issue.

Instead, send a detailed report to **[INSERT SECURITY EMAIL]**.

Please include:

- A clear description of the vulnerability
- Steps to reproduce the issue
- Affected versions/components
- Any potential mitigations you've identified

You should receive a response within **48 hours**. If the issue is confirmed,
we will release a patch as soon as possible depending on complexity.

## Security Considerations for FridgeAI

This project connects to IoT hardware and external APIs. When deploying:

- **API Keys**: Never commit `.env` files or hardcode credentials
- **Network**: Run behind a reverse proxy (nginx/Caddy) with HTTPS
- **Neo4j & Milvus**: Secure with strong passwords and restrict to localhost
  when possible
- **OneNET MQTT**: Use device-level authentication tokens, not master keys
- **WebSocket**: The `/ws/chat` endpoint does not implement authentication -
  use a reverse proxy to add auth layer in production

## Known Issues

See [Known Limitations](README.md#%EF%B8%8F-known-limitations--%E5%B7%B2%E7%9F%A5%E9%99%90%E5%88%B6) in the README for currently documented security-relevant limitations.
