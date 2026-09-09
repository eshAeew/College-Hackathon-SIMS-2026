"""FastAPI routes for the Intentionally Flawed Demo Target API."""
import asyncio
import random
import time
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.demo_target.config import get_demo_config

demo_target_router = APIRouter(prefix="/demo-api", tags=["Demo Target API (Intentionally Flawed)"])


# ---------------------------------------------------------
# Bug 1: POST /demo-api/auth/login -> Missing Input Validation / Unhandled 500
# ---------------------------------------------------------
@demo_target_router.post("/auth/login", summary="1. Auth Login (Injected 500 Crash)")
async def demo_login(request: Request):
    """
    Demo Bug #1:
    - Flawed mode: throws unhandled KeyError causing HTTP 500 when password is omitted.
    - Fixed mode: returns 400 Bad Request with clean error envelope.
    """
    config = get_demo_config()
    config.increment_hit("login")

    try:
        data = await request.json()
    except Exception:
        data = {}

    if config.unhandled_500_login:
        # BUG: Direct dictionary access without presence checks or exception guards
        # If 'password' or 'username' is missing, Python raises KeyError -> uncaught 500!
        user = data["username"]
        pwd = data["password"]
        if pwd == "secret123":
            return {"token": "jwt-demo-token-xyz-12345", "user": user, "status": "authenticated"}
        return JSONResponse(status_code=401, content={"detail": "Invalid credentials"})
    else:
        # FIXED: Proper input validation and 400 rejection
        if not data or "username" not in data or "password" not in data:
            return JSONResponse(
                status_code=400,
                content={"error": "MissingRequiredField", "detail": "Fields 'username' and 'password' are required."},
            )
        if data["password"] == "secret123":
            return {"token": "jwt-demo-token-xyz-12345", "user": data["username"], "status": "authenticated"}
        return JSONResponse(status_code=401, content={"error": "InvalidCredentials", "detail": "Invalid password."})


# ---------------------------------------------------------
# Bug 2: GET /demo-api/products -> Sluggish Performance / SLA Breach (>1.5s)
# ---------------------------------------------------------
@demo_target_router.get("/products", summary="2. Product Catalog (Injected Latency Spike)")
async def demo_products(latency_spike: Optional[bool] = None):
    """
    Demo Bug #2:
    - Flawed mode: Injects a 1.2s - 1.5s asyncio sleep to simulate unindexed SQL queries.
    - Fixed mode: Responds instantly in <5ms.
    """
    config = get_demo_config()
    config.increment_hit("products")

    should_delay = config.slow_latency_products if latency_spike is None else latency_spike
    if should_delay:
        await asyncio.sleep(1.2)  # Simulated unindexed join query lag

    return {
        "catalog": "Alpha Demo Store",
        "total_items": 3,
        "products": [
            {"id": 1, "name": "Mechanical Keyboard RGB", "category": "peripherals", "price": 89.99},
            {"id": 2, "name": "Wireless Ergonomic Mouse", "category": "peripherals", "price": 49.99},
            {"id": 3, "name": "Ultra HD 4K Monitor", "category": "displays", "price": 329.99},
        ],
        "latency_simulated": should_delay,
    }


# ---------------------------------------------------------
# Bug 3: GET /demo-api/products/{id} -> Schema Drift / Type Inversion
# ---------------------------------------------------------
@demo_target_router.get("/products/{product_id}", summary="3. Product Details (Injected Schema Drift)")
async def demo_product_detail(product_id: int):
    """
    Demo Bug #3:
    - Flawed mode: returns price as string ("89.99 USD"), boolean as string, and omits stock.
    - Fixed mode: returns strict schema (price: float, stock: int, available: bool).
    """
    config = get_demo_config()
    config.increment_hit("product_detail")

    if config.schema_drift_product_detail:
        # BUG: String price, boolean string, missing 'stock' int
        return {
            "id": product_id,
            "name": "Mechanical Keyboard RGB",
            "price": "89.99 USD",  # Schema violation: should be float
            "available": "true",    # Schema violation: should be boolean
            # Missing required field: 'stock'
        }
    else:
        # FIXED: Proper contract types
        return {
            "id": product_id,
            "name": "Mechanical Keyboard RGB",
            "price": 89.99,
            "available": True,
            "stock": 142,
        }


# ---------------------------------------------------------
# Bug 4: POST /demo-api/orders -> Intermittent 503 Gateway Flakiness
# ---------------------------------------------------------
@demo_target_router.post("/orders", summary="4. Create Order (Injected Flakiness / Intermittent 503)")
async def demo_create_order(request: Request, force_fail: Optional[bool] = None):
    """
    Demo Bug #4:
    - Flawed mode: Throws HTTP 503 Service Unavailable randomly (or on force_fail).
    - Fixed mode: Deterministically creates the order and returns 201 Created.
    """
    config = get_demo_config()
    config.increment_hit("orders")

    try:
        payload = await request.json()
    except Exception:
        payload = {"product_id": 1, "quantity": 1}

    if config.flaky_503_orders:
        is_failing = force_fail if force_fail is not None else (random.random() < 0.45)
        if is_failing:
            return Response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content="503 Service Unavailable: Downstream Payment Gateway Timeout (Transient Flake)",
                media_type="text/plain",
            )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "order_id": f"ORD-{random.randint(10000, 99999)}",
            "status": "CONFIRMED",
            "product_id": payload.get("product_id", 1),
            "quantity": payload.get("quantity", 1),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


# ---------------------------------------------------------
# Bug 5: GET /demo-api/users/profile -> Malformed Payload / Syntax Corrupt
# ---------------------------------------------------------
@demo_target_router.get("/users/profile", summary="5. User Profile (Injected Malformed JSON)")
async def demo_user_profile(corrupt: Optional[bool] = None):
    """
    Demo Bug #5:
    - Flawed mode: Emits invalid truncated JSON payload with application/json header.
    - Fixed mode: Emits clean valid JSON response.
    """
    config = get_demo_config()
    config.increment_hit("profile")

    should_corrupt = config.malformed_json_profile if corrupt is None else corrupt
    if should_corrupt:
        # BUG: Truncated malformed JSON payload that fails client parser
        bad_json = '{"user_id": 42, "username": "sentinel_tester", "email": "tester@sentinel.io", "preferences": {"theme": "dark", "notifications":'
        return Response(content=bad_json, media_type="application/json", status_code=200)

    return {
        "user_id": 42,
        "username": "sentinel_tester",
        "email": "tester@sentinel.io",
        "preferences": {"theme": "dark", "notifications": True},
        "role": "QA_ENGINEER",
    }


# ---------------------------------------------------------
# Bug 6: POST /demo-api/cart/checkout -> State Leak & Regression Bug
# ---------------------------------------------------------
@demo_target_router.post("/cart/checkout", summary="6. Cart Checkout (Injected Regression Bug)")
async def demo_checkout():
    """
    Demo Bug #6:
    - Flawed mode: Succeeds on 1st execution, fails with HTTP 409 on subsequent runs (state leak).
    - Fixed mode: Succeeds deterministically on all executions.
    """
    config = get_demo_config()
    config.increment_hit("checkout")

    if config.state_leak_checkout:
        config.checkout_invocations += 1
        if config.checkout_invocations > 1:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "error": "InventoryLockConflict",
                    "detail": f"Checkout session locked. Uncommitted state leak from execution #{config.checkout_invocations - 1}.",
                    "run_invocation": config.checkout_invocations,
                },
            )

    return {
        "status": "CHECKOUT_SUCCESSFUL",
        "cart_total": 139.98,
        "transaction_id": f"TXN-{random.randint(100000, 999999)}",
        "invocation": config.checkout_invocations,
    }


# ---------------------------------------------------------
# Bug Control & Demonstration Management Endpoints
# ---------------------------------------------------------
@demo_target_router.get("/control/status", summary="Get Demo Bug States & Telemetry")
def get_control_status():
    """Retrieve current state of all 6 injected bug flags and endpoint hits."""
    return get_demo_config().get_status()


@demo_target_router.post("/control/toggle/{bug_name}", summary="Toggle Individual Bug")
def toggle_bug(bug_name: str):
    """Toggle an individual bug between FLAWED and FIXED."""
    try:
        new_state = get_demo_config().toggle(bug_name)
        return {"bug_name": bug_name, "is_active": new_state, "message": f"Bug '{bug_name}' set to {new_state}"}
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@demo_target_router.post("/control/fix-all", summary="Fix All Demo API Bugs")
def fix_all_bugs():
    """Set all 6 demo bugs to FIXED mode (used for demonstrating resolution)."""
    get_demo_config().fix_all()
    return {"status": "all_fixed", "message": "All 6 demo API bugs have been resolved."}


@demo_target_router.post("/control/reset", summary="Reset All Demo API Bugs to Flawed")
def reset_all_bugs():
    """Reset all 6 demo bugs to FLAWED mode."""
    get_demo_config().reset()
    return {"status": "reset_to_flawed", "message": "All 6 demo API bugs have been re-enabled."}


@demo_target_router.get("/openapi.json", include_in_schema=False, summary="Demo API OpenAPI Specification")
def get_demo_openapi():
    """Generate and return OpenAPI 3.1.0 specification for the demo e-commerce target."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Alpha Commerce Demo Store API",
            "version": "1.0.0",
            "description": "Intentionally Flawed Target API for API Sentinel quality and failure diagnostics.",
        },
        "paths": {
            "/demo-api/auth/login": {
                "post": {
                    "summary": "User Login",
                    "operationId": "demoLogin",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password"],
                                    "properties": {
                                        "username": {"type": "string", "example": "admin"},
                                        "password": {"type": "string", "example": "secret123"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Authenticated"},
                        "400": {"description": "Bad Request"},
                        "401": {"description": "Unauthorized"},
                        "500": {"description": "Server Crash (Bug 1)"},
                    },
                }
            },
            "/demo-api/products": {
                "get": {
                    "summary": "List Products",
                    "operationId": "demoListProducts",
                    "responses": {
                        "200": {"description": "Product catalog list"},
                    },
                }
            },
            "/demo-api/products/{product_id}": {
                "get": {
                    "summary": "Get Product Detail",
                    "operationId": "demoGetProduct",
                    "parameters": [
                        {"name": "product_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                    ],
                    "responses": {
                        "200": {
                            "description": "Product details",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["id", "name", "price", "stock", "available"],
                                        "properties": {
                                            "id": {"type": "integer"},
                                            "name": {"type": "string"},
                                            "price": {"type": "number"},
                                            "stock": {"type": "integer"},
                                            "available": {"type": "boolean"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/demo-api/orders": {
                "post": {
                    "summary": "Create Order",
                    "operationId": "demoCreateOrder",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "product_id": {"type": "integer", "example": 1},
                                        "quantity": {"type": "integer", "example": 2},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {"description": "Order Created"},
                        "503": {"description": "Intermittent Gateway Timeout (Bug 4)"},
                    },
                }
            },
            "/demo-api/users/profile": {
                "get": {
                    "summary": "Get User Profile",
                    "operationId": "demoUserProfile",
                    "responses": {
                        "200": {"description": "User profile JSON"},
                    },
                }
            },
            "/demo-api/cart/checkout": {
                "post": {
                    "summary": "Cart Checkout",
                    "operationId": "demoCheckout",
                    "responses": {
                        "200": {"description": "Checkout successful"},
                        "409": {"description": "State leak lock conflict (Bug 6)"},
                    },
                }
            },
        },
    }
