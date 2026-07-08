"""
MCP server that exposes the warranty-coverage capability as a tool.

This wraps the provided `check_warranty_coverage` function (from
`warranty_module`) and publishes it over the Model Context Protocol. The
FastAPI service connects to this server as an MCP client (see `main.py`) and
invokes the tool with the fields extracted from the repair order.

Run standalone for debugging:
    python warranty_server.py
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from warranty_module import check_warranty_coverage

mcp = FastMCP("warranty")


@mcp.tool()
def warranty_coverage(
    vin: str,
    make: str,
    model: str,
    year: int,
    mileage: int,
    part_number: str,
) -> str:
    """Check warranty coverage for a vehicle and repair part.

    Returns a JSON string. On success:
        {"eligible": bool, "reason": str, "warranty_type": str}
    On invalid input (bad VIN or unknown make/model):
        {"error": str}

    Errors are returned as structured JSON (rather than raised) so the client
    can map them to an HTTP status independently of MCP-adapter error semantics.
    """
    try:
        result = check_warranty_coverage(
            vin=vin,
            make=make,
            model=model,
            year=year,
            mileage=mileage,
            part_number=part_number,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    # Return JSON text so the result is unambiguous across MCP/adapter versions.
    return json.dumps(result)


if __name__ == "__main__":
    # stdio transport: the client spawns this process and talks over stdin/stdout.
    mcp.run(transport="stdio")
