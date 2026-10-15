---
name: implementation-plan
description: Master implementation plan for Ghost Cursor project
metadata:
  type: project
---

# Ghost Cursor Implementation Plan

## Phase 1: Monorepo Setup & Core Infrastructure
- [ ] Initialize npm workspace monorepo structure
- [ ] Create package.json with workspace configuration
- [ ] Create tsconfig.json for TypeScript strict mode
- [ ] Set up .gitignore, .dockerignore
- [ ] Create MEMORY.md with detailed implementation tracking

## Phase 2: Frontend SDK (@ghost-cursor/sdk)
- [ ] Build core executor engine with Element Targeting Cascade
- [ ] Implement native value setters for React/Vue compatibility
- [ ] Build Shadow DOM chat widget (Preact-based)
- [ ] Implement AI Cursor animation system
- [ ] Build Tour Overlay engine
- [ ] Create Context Provider for DOM scanning
- [ ] Build WebSocket transport layer
- [ ] Create React wrapper (@ghost-cursor/sdk-react)

## Phase 3: Python Backend SDK (ghost-cursor)
- [ ] Create pyproject.toml and package structure
- [ ] Implement GhostCursorBackend proxy class
- [ ] Build SQLAlchemyChatStore for customer DB persistence
- [ ] Implement Brain Loader (platform.md + pages/*.md)
- [ ] Create FastAPI/Flask/Django integrations
- [ ] Build Gateway Loopback protocol for tool execution

## Phase 4: Orchestrator Service (services/orchestrator)
- [ ] Set up FastAPI app with Google ADK agent
- [ ] Implement Vertex AI Gemini 2.0 integration
- [ ] Create Frontend Action Tools (navigate, click, fill_input, toggle_switch, guided_tour, ask_clarification)
- [ ] Build run state management with PostgreSQL/Firestore
- [ ] Implement revision tracking and deduplication
- [ ] Add mock provider for local testing

## Phase 5: ShopHive Demo Application
- [ ] Build React 18 + Vite + TailwindCSS frontend
- [ ] Create pages: Home, ProductDetail, Cart, Checkout, Orders, Settings
- [ ] Add data-ghost-id attributes to interactive elements
- [ ] Build FastAPI backend with proxy routes
- [ ] Register customer backend tools (lookup_order, check_warehouse_stock, simulate_discount_roi)
- [ ] Create Brain markdown files (platform.md + pages/*.md)
- [ ] Run database migration for chat history

## Phase 6: Testing & Integration
- [ ] Unit tests for protocol validation
- [ ] Playwright browser tests for ShopHive demo
- [ ] Integration tests for gateway loopback
- [ ] Verify all showcase scenarios work

## Phase 7: Documentation & Deployment
- [ ] Generate INTEGRATION.md, PROVIDERS.md, GCP.md, OPERATIONS.md
- [ ] Create Docker configurations
- [ ] Set up Cloud Build and deployment scripts
- [ ] Verify README.md and demo scripts

## Current Status: Phase 1 - Starting