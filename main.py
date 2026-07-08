"""
Warranty-claim analysis API.

Flow for POST /analyze-claim:
  1. Extract structured fields from the repair-order text using LangChain +
     Claude (`ChatAnthropic` with structured output).
  2. Look up warranty coverage by invoking an MCP tool (served by
     `warranty_server.py`) with the extracted fields.
  3. Return the merged result.

LangChain is the LLM orchestration layer; the warranty capability is reached
over the Model Context Protocol, with the MCP tool surfaced to LangChain via
`langchain-mcp-adapters`.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import ToolException
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

from models import AnalyzeClaimRequest, AnalyzeClaimResponse, ExtractedClaim

MODEL = "claude-opus-4-8"
MCP_TOOL_NAME = "warranty_coverage"

_EXTRACTION_SYSTEM = (
    "You extract structured data from automotive repair-order (RO) text. "
    "Return exactly the requested fields. Normalize the mileage to an integer "
    "with no commas, and keep the repair description concise."
)


def _parse_coverage(raw: object) -> dict:
    """Normalize the MCP tool's return value into a coverage dict.

    `langchain-mcp-adapters` may return the result as a dict, a JSON string, or
    a list of content blocks (e.g. ``[{"type": "text", "text": "<json>"}]``).
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        raw = "".join(
            block.get("text", "")
            for block in raw
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return json.loads(raw)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start a persistent MCP client session to the warranty server."""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).parent / "warranty_server.py")],
    )

    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        # Load the MCP tools as LangChain tools and pick out the warranty tool.
        tools = await load_mcp_tools(session)
        warranty_tool = next(t for t in tools if t.name == MCP_TOOL_NAME)

        app.state.warranty_tool = warranty_tool
        app.state.extractor = ChatAnthropic(
            model=MODEL, max_tokens=1024
        ).with_structured_output(ExtractedClaim)

        yield
        # AsyncExitStack tears down the session and subprocess on shutdown.


app = FastAPI(title="Warranty Claim Analyzer", lifespan=lifespan)

# Expose Prometheus metrics at /metrics (request counts, latencies, status codes).
Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze-claim", response_model=AnalyzeClaimResponse)
async def analyze_claim(request: AnalyzeClaimRequest) -> AnalyzeClaimResponse:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not set.")

    # 1. Extract structured fields from the RO text via LangChain + Claude.
    try:
        extracted: ExtractedClaim = await app.state.extractor.ainvoke(
            [
                ("system", _EXTRACTION_SYSTEM),
                ("human", request.ro_text),
            ]
        )
    except Exception as exc:  # noqa: BLE001 - surface extraction failures cleanly
        raise HTTPException(
            status_code=502, detail=f"Field extraction failed: {exc}"
        ) from exc

    # 2. Check warranty coverage via the MCP tool, using the extracted fields.
    try:
        raw = await app.state.warranty_tool.ainvoke(
            {
                "vin": extracted.vin,
                "make": extracted.make,
                "model": extracted.model,
                "year": extracted.year,
                "mileage": extracted.mileage,
                "part_number": extracted.part_number,
            }
        )
        coverage = _parse_coverage(raw)
    except (ToolException, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Warranty lookup failed: {exc}"
        ) from exc

    # A structured error (bad VIN / unknown make/model) -> client error.
    if "error" in coverage:
        raise HTTPException(status_code=422, detail=coverage["error"])

    # 3. Merge and return.
    return AnalyzeClaimResponse(
        vin=extracted.vin,
        year=extracted.year,
        make=extracted.make,
        model=extracted.model,
        mileage=extracted.mileage,
        repair_description=extracted.repair_description,
        part_number=extracted.part_number,
        labor_hours=extracted.labor_hours,
        coverage_eligible=coverage["eligible"],
        coverage_reason=coverage["reason"],
    )
