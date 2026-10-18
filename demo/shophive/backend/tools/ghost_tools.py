#!/usr/bin/env python3
"""
Ghost Cursor Customer Backend Tools

Customer-registered read-only tools for ShopHive demo.
These tools are executed locally on the customer backend via Gateway Loopback.
"""

import os
import asyncio
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from ghost_cursor import GhostCursorBackend
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

try:
    from shop_data import fetch_order, fetch_stock
except ImportError:
    from ..shop_data import fetch_order, fetch_stock


# ============================================================================
# Typed Parameter Models
# ============================================================================

class OrderQuery(BaseModel):
    """Query parameters for order lookup"""
    order_id: str = Field(
        ...,
        description="Order ID to lookup, e.g., 'SH-1024'"
    )


class StockQuery(BaseModel):
    """Query parameters for warehouse stock check"""
    sku: str = Field(
        ...,
        description="Product SKU code, e.g., 'NK-AM90-01'"
    )
    size: str = Field(
        ...,
        description="Shoe size, e.g., '10' or '11.5'"
    )


class DiscountQuery(BaseModel):
    """Query parameters for discount ROI calculation"""
    promo_code: str = Field(
        ...,
        description="Promotional code to test, e.g., 'SAVE20'"
    )
    subtotal: float = Field(
        ...,
        description="Current cart subtotal before discount"
    )


# ============================================================================
# Tool Registration
# ============================================================================

def register_shophive_tools(ghost: GhostCursorBackend, engine: Optional[AsyncEngine] = None):
    """
    Register customer-specific read-only tools with Ghost Cursor.
    These tools execute locally on the customer backend.
    """
    if engine is None:
        db_url = os.getenv("SHOPHIVE_DATABASE_URL", "sqlite+aiosqlite:///./shophive.db")
        if db_url.startswith("sqlite:///"):
            db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        engine = create_async_engine(db_url)

    @ghost.register_tool(
        name="lookup_order",
        description="Checks order status, shipment tracking, and items for the authenticated user",
        schema=OrderQuery.model_json_schema(),
        read_only=True,
    )
    async def lookup_order(params: OrderQuery, context: Dict[str, Any]):
        """
        Look up an order by ID.

        This tool queries the customer's database
        to retrieve order information.
        """
        user_id = context.get("user_id", "")
        order = await fetch_order(engine, params.order_id, user_id)
        if order:
            return {
                "order_id": order["order_id"],
                "customer_name": order["customer_name"],
                "items": order["items"],
                "total": order["total"],
                "status": order["status"],
                "tracking_number": order["tracking_number"],
                "carrier": order["carrier"],
                "shipped_date": order["shipped_date"],
                "estimated_delivery": order["estimated_delivery"],
            }
        return {
            "error": f"Order {params.order_id} not found",
        }

    @ghost.register_tool(
        name="check_warehouse_stock",
        description="Checks available inventory count for a specific shoe SKU and size",
        schema=StockQuery.model_json_schema(),
        read_only=True,
    )
    async def check_warehouse_stock(params: StockQuery, context: Dict[str, Any]):
        """
        Check warehouse inventory for a specific SKU and size.

        This tool queries the customer's inventory system
        to check product availability.
        """
        units = await fetch_stock(engine, params.sku, params.size)
        if units is not None:
            return {
                "sku": params.sku,
                "size": params.size,
                "available_units": units,
                "unit_message": f"{units} units available" if units > 0 else "Out of stock",
            }
        return {
            "sku": params.sku,
            "size": params.size,
            "available_units": 0,
            "unit_message": "SKU not found",
        }

    @ghost.register_tool(
        name="simulate_discount_roi",
        description="Calculates business margin sensitivity for a promotional code",
        schema=DiscountQuery.model_json_schema(),
        read_only=True,
    )
    async def simulate_discount_roi(params: DiscountQuery, context: Dict[str, Any]):
        """
        Simulate the ROI impact of a discount promotion.

        This tool helps merchants understand the business impact
        of offering discounts.
        """
        user_id = context.get("user_id", "anonymous")

        # Mock calculation
        current_margin_percent = 35.0  # 35% margin
        promo_discount_percent = 20.0 if params.promo_code == "SAVE20" else 10.0

        new_margin_percent = current_margin_percent - promo_discount_percent
        break_even_increase_percent = (promo_discount_percent / (100 - promo_discount_percent)) * 100

        sensitivity = [
            {
                "factor": "Discount %",
                "impact": "high",
                "direction": "negative",
                "description": "Higher discounts reduce margins significantly"
            },
            {
                "factor": "Order Volume",
                "impact": "high",
                "direction": "positive",
                "description": "Promotions often increase order volume"
            },
            {
                "factor": "Avg Order Value",
                "impact": "medium",
                "direction": "neutral",
                "description": "Customers may buy more to qualify for discount"
            },
        ]

        return {
            "promo_code": params.promo_code,
            "discount_percent": promo_discount_percent,
            "current_margin_percent": current_margin_percent,
            "projected_margin_percent": new_margin_percent,
            "margin_impact_percent": -promo_discount_percent,
            "break_even_increase_percent": round(break_even_increase_percent, 1),
            "break_even_volume_multiplier": round(break_even_increase_percent / 100 + 1, 2),
            "sensitivity": sensitivity,
            "cards": [
                {
                    "type": "metric",
                    "label": "Projected Margin",
                    "value": f"{new_margin_percent:.0f}%",
                    "delta": f"-{promo_discount_percent:.0f}%",
                },
                {
                    "type": "bars",
                    "series": [
                        {"label": "Current", "value": current_margin_percent},
                        {"label": params.promo_code, "value": new_margin_percent},
                        {"label": "Break-even Vol", "value": round(break_even_increase_percent, 1)},
                    ],
                },
            ],
        }