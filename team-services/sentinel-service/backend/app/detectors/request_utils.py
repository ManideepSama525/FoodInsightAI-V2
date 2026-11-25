from urllib.parse import unquote, unquote_plus


def extract_request_payload(request):
    """
    Extract and normalize request body, query and path.

    This function only inspects strings. It never executes payloads.
    """
    parts = []

    for key in ("body", "query", "path"):
        value = request.get(key, "")

        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")

        if value is None:
            continue

        value = str(value)

        for _ in range(3):
            if key == "query":
                decoded = unquote_plus(value)
            else:
                decoded = unquote(value)

            if decoded == value:
                break

            value = decoded

        parts.append(value)

    return " ".join(parts).lower()