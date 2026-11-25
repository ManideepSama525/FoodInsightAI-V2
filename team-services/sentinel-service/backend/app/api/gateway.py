from fastapi import APIRouter, Request
from fastapi.responses import Response
import httpx

router = APIRouter(
    prefix="/gateway",
    tags=["Security Gateway"],
)

# ---------------------------------------------------------
# Demo Application
# ---------------------------------------------------------

DEMO_APP = "http://127.0.0.1:9000"


# ---------------------------------------------------------
# Forward Request
# ---------------------------------------------------------

async def forward_request(
    request: Request,
    path: str,
):
    target_url = f"{DEMO_APP}/{path.lstrip('/')}"

    # Preserve query parameters
    if request.url.query:
        target_url += f"?{request.url.query}"

    body = await request.body()

    # Copy useful headers
    headers = dict(request.headers)

    # These are controlled by the proxy
    headers.pop("host", None)
    headers.pop("content-length", None)

    async with httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=False,
    ) as client:

        response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
        )

    # Return demo application's response
    response_headers = dict(response.headers)

    # Remove hop-by-hop headers
    response_headers.pop("content-length", None)
    response_headers.pop("transfer-encoding", None)
    response_headers.pop("connection", None)

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type"),
    )


# ---------------------------------------------------------
# Gateway Root
# ---------------------------------------------------------

@router.api_route(
    "/",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    ],
)
async def gateway_root(
    request: Request,
):
    return await forward_request(
        request,
        "",
    )


# ---------------------------------------------------------
# Gateway Catch-All
# ---------------------------------------------------------

@router.api_route(
    "/{path:path}",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    ],
)
async def gateway(
    path: str,
    request: Request,
):
    return await forward_request(
        request,
        path,
    )