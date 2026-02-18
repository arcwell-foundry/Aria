"""ARIA MCP Servers — Model Context Protocol tool exposure layer.

Exposes ARIA's API integrations (Life Sciences, Exa, Business Tools) as
MCP servers.  Agents interact via MCPToolClient; external MCP clients
connect via SSE endpoints mounted on FastAPI.

Servers:
    aria-lifesci   — PubMed, ClinicalTrials.gov, FDA, ChEMBL
    aria-exa       — Exa web search, news, similarity, answer, research
    aria-business  — Calendar, CRM, and email via Composio
"""
