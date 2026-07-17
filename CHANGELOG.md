# Changelog

All notable changes to FridgeAI will be documented in this file.

## [Unreleased]

### Planned
- Docker/CI-CD pipeline
- PostgresSaver/PostgresStore migration
- Recipe favorites & weekly meal planning
- Authentication & credential management

## [2026-07-16] — Auth + PersistentStore + RAG Enhancements

### Added
- Auth module for API access control
- PersistentStore for user preferences
- Enhanced Agent/RAG with optimized prompts and retrieval
- Expanded test suite (50 RAG + 20 Agent test cases)

## [2026-07-12] — Documentation & Community

### Added
- Professional README with architecture diagrams (Mermaid)
- MIT LICENSE
- CONTRIBUTING.md with development workflow
- Community files: Issue/PR templates

## [2026-07-12] — DeepSeek Fixes & Test Suite

### Fixed
- DeepSeek thinking mode disabled for stable output
- Synonym dictionary expanded (80+ groups)
- JSON field normalization for consistent parsing

### Added
- Complete test suite (Ragas + DeepEval for RAG evaluation)

## [2026-07-09] — Bug Fixes & UI Optimization

### Fixed
- 11 bugs: sub-agent connectivity, recipe search, detail rendering, scroll issues, type safety
- UI refactoring with AI readability improvements

## [2026-07-09] — Initial Release

### Added
- Phase 1-6: IoT integration, RAG system, Agent framework, Frontend app
- 323 Chinese recipes across 12 categories
- LangGraph StateGraph with 3 sub-agents + 5 middleware layers
- Neo4j + Milvus hybrid GraphRAG retrieval
- WebSocket streaming chat with Human-in-the-Loop
- OneNET MQTT real-time fridge inventory sync
- uni-app cross-platform frontend (Vue 3)
