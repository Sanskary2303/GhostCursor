"""ShopHive demo data in the customer's own database (SQLite by default)."""
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

metadata = sa.MetaData()

shop_orders = sa.Table(
    "shop_orders",
    metadata,
    sa.Column("order_id", sa.String(32), primary_key=True),
    sa.Column("owner", sa.String(128), nullable=False, index=True),
    sa.Column("customer_name", sa.String(128), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("carrier", sa.String(32), nullable=False),
    sa.Column("tracking_number", sa.String(64), nullable=False),
    sa.Column("shipped_date", sa.String(16), nullable=False),
    sa.Column("estimated_delivery", sa.String(16), nullable=False),
    sa.Column("total", sa.Float, nullable=False),
    sa.Column("items", sa.JSON, nullable=False),
)

shop_inventory = sa.Table(
    "shop_inventory",
    metadata,
    sa.Column("sku", sa.String(32), primary_key=True),
    sa.Column("size", sa.String(8), primary_key=True),
    sa.Column("units", sa.Integer, nullable=False),
)

SEED_ORDERS = [
    {
        "order_id": "SH-1024",
        "owner": "user_demo",
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
    {
        "order_id": "SH-987",
        "owner": "user_other",
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
]

SEED_INVENTORY = [
    {"sku": "NK-AM90-01", "size": "10", "units": 20},
    {"sku": "NK-AM90-01", "size": "11", "units": 8},
    {"sku": "NK-AM90-01", "size": "12", "units": 5},
    {"sku": "NK-AM90-01", "size": "13", "units": 3},
    {"sku": "NK-AJ1-01", "size": "10", "units": 16},
    {"sku": "NK-AJ1-01", "size": "11", "units": 9},
    {"sku": "NK-AJ1-01", "size": "12", "units": 4},
    {"sku": "NK-Y350-01", "size": "10", "units": 12},
    {"sku": "NK-UB22-01", "size": "10", "units": 15},
    {"sku": "NK-UB22-01", "size": "11", "units": 8},
]


async def seed_shop_data(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        if (await conn.execute(sa.select(sa.func.count()).select_from(shop_orders))).scalar_one() == 0:
            await conn.execute(shop_orders.insert(), SEED_ORDERS)
        if (await conn.execute(sa.select(sa.func.count()).select_from(shop_inventory))).scalar_one() == 0:
            await conn.execute(shop_inventory.insert(), SEED_INVENTORY)


async def fetch_order(engine: AsyncEngine, order_id: str, owner: str) -> Optional[Dict[str, Any]]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                sa.select(shop_orders).where(shop_orders.c.order_id == order_id, shop_orders.c.owner == owner)
            )
        ).mappings().first()
        return dict(row) if row else None


async def fetch_stock(engine: AsyncEngine, sku: str, size: str) -> Optional[int]:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                sa.select(shop_inventory.c.units).where(shop_inventory.c.sku == sku, shop_inventory.c.size == size)
            )
        ).scalar_one_or_none()

