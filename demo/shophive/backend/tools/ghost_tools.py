#!/usr/bin/env python3
"""
Ghost Cursor Customer Backend Tools

Customer-registered read-only tools for ShopHive demo.
These tools are executed locally on the customer backend via Gateway Loopback.
"""

from pydantic import BaseModel, Field
from ghost_cursor import GhostCursorBackend
import asyncio
from typing import Any, Dict


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

def register_shophive_tools(ghost: GhostCursorBackend):
    """
    Register customer-specific read-only tools with Ghost Cursor.
    These tools execute locally on the customer backend.
    """

    # Mock database for demo
    mock_orders = {
        "SH-1024": {
            "order_id": "SH-1024",
            "customer_name": "John Doe",
            "items": [
                {"name": "Nike Air Max 90", "size": "10", "price": 129.99, "quantity": 1},
            ],
            "total": 129.99,
            "status": "Shipped",
            "tracking_number": "1Z999AA10123456784",
            "carrier": "UPS",
            "shipped_date": "2024-01-17",
            "estimated_delivery": "2024-01-20",
        },
        "SH-987": {
            "order_id": "SH-987",
            "customer_name": "Jane Smith",
            "items": [
                {"name": "Air Jordan 1 Retro", "size": "10", "price": 179.99, "quantity": 1},
            ],
            "total": 179.99,
            "status": "Delivered",
            "tracking_number": "1Z999AA10123456780",
            "carrier": "FedEx",
            "shipped_date": "2024-01-12",
            "estimated_delivery": "2024-01-15",
        },
    }

    mock_inventory = {
        ("NK-AM90-01", "10"): 20,
        ("NK-AM90-01", "11"): 8,
        ("NK-AM90-01", "12"): 5,
        ("NK-AM90-01", "13"): 3,
        ("NK-AJ1-01", "10"): 16,
        ("NK-AJ1-01", "11"): 9,
        ("NK-AJ1-01", "12"): 4,
        ("NK-Y350-01", "10"): 12,
        ("NK-UB22-01", "10"): 15,
        ("NK-UB22-01", "11"): 8,
    }

    @ghost.register_tool(
        name="lookup_order",
        description="Checks order status, shipment tracking, and items for the authenticated user",
        schema=OrderQuery.model_json_schema(),
        read_only=True,
    )
    async def lookup_order(params: OrderQuery, context: Dict[str, Any]):
        """
        Look up an order by ID.

        This tool simulates querying the customer's PostgreSQL database
        to retrieve order information.
        """
        user_id = context.get("user_id", "anonymous")

        # In production, this would query the actual database
        # order = await fetch_order_from_db(params.order_id, user_id)

        # For demo, return mock data if order exists
        if params.order_id in mock_orders:
            order = mock_orders[params.order_id]
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
        else:
            return {
                "error": f"Order {params.order_id} not found or unauthorized access",
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

        This tool simulates querying the customer's inventory system
        to check product availability.
        """
        user_id = context.get("user_id", "anonymous")

        # In production, this would query the actual inventory system
        # stock = await query_inventory_system(params.sku, params.size)

        # For demo, return mock data
        key = (params.sku, params.size)
        if key in mock_inventory:
            units = mock_inventory[key]
            return {
                "sku": params.sku,
                "size": params.size,
                "available_units": units,
                "unit_message": f"{units} units available" if units > 0 else "Out of stock",
            }
        else:
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
        }