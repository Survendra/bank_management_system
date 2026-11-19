import re


QUERY_PARAMETERS = {
    "staff_customer_search": {
        "q": "string",
        "page": "integer",
        "page_size": "integer",
    },
    "staff_transaction_search": {
        "q": "string",
        "account_number": "string",
        "type": "string",
        "status": "string",
        "from": "string",
        "to": "string",
        "min_amount": "number",
        "max_amount": "number",
        "page": "integer",
        "page_size": "integer",
    },
    "staff_audit_log": {
        "actor": "string",
        "action": "string",
        "entity_id": "string",
        "from": "string",
        "to": "string",
        "page": "integer",
        "page_size": "integer",
    },
    "staff_disputes": {
        "status": "string",
    },
}


def _convert_path(rule):
    parameters = []

    def replace(match):
        converter = match.group("converter") or "string"
        name = match.group("name")
        schema = {
            "type": "integer" if converter == "int" else "string",
        }
        parameters.append({
            "name": name,
            "in": "path",
            "required": True,
            "schema": schema,
        })
        return "{" + name + "}"

    path = re.sub(
        r"<(?:(?P<converter>[^:<>]+):)?(?P<name>[^<>]+)>",
        replace,
        rule,
    )
    return path, parameters


def _response_schema():
    return {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "message": {"type": "string"},
        },
        "additionalProperties": True,
    }


def build_openapi_spec(flask_app):
    paths = {}
    for rule in flask_app.url_map.iter_rules():
        if (
            rule.endpoint == "static"
            or rule.rule == "/openapi.json"
            or rule.rule == "/docs"
            or rule.rule.startswith("/docs/")
        ):
            continue
        path, path_parameters = _convert_path(rule.rule)
        path_item = paths.setdefault(path, {})
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            operation_id = re.sub(
                r"[^a-zA-Z0-9_]",
                "_",
                f"{rule.endpoint}_{method.lower()}",
            )
            operation = {
                "operationId": operation_id,
                "summary": rule.endpoint.replace("_", " ").title(),
                "description": (
                    "Uses the same-origin Flask session cookie when the endpoint "
                    "requires authentication. Sign in through the relevant login "
                    "endpoint first."
                ),
                "tags": [path.strip("/").split("/")[1] if path.startswith("/api/") else "API"],
                "parameters": list(path_parameters),
                "responses": {
                    "200": {
                        "description": "Request completed.",
                        "content": {
                            "application/json": {
                                "schema": _response_schema(),
                            },
                        },
                    },
                    "201": {
                        "description": "Resource created.",
                        "content": {
                            "application/json": {
                                "schema": _response_schema(),
                            },
                        },
                    },
                    "default": {
                        "description": "Error response.",
                        "content": {
                            "application/json": {
                                "schema": _response_schema(),
                            },
                        },
                    },
                },
            }
            if method == "GET":
                for name, value_type in QUERY_PARAMETERS.get(
                    rule.endpoint,
                    {},
                ).items():
                    operation["parameters"].append({
                        "name": name,
                        "in": "query",
                        "required": False,
                        "schema": {"type": value_type},
                    })
            if method in {"POST", "PUT", "PATCH"}:
                operation["requestBody"] = {
                    "required": False,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                        },
                    },
                }
            path_item[method.lower()] = operation

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "BlueBank API",
            "version": "1.0.0",
            "description": (
                "Interactive API documentation. Open this page on the same host "
                "as the API so browser session cookies are sent automatically."
            ),
        },
        "servers": [{"url": "/", "description": "Current API host"}],
        "paths": paths,
    }
