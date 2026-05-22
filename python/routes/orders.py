from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from bson import ObjectId

from database import orders_collection, products_collection
from models.order import OrderRequest
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/orders", tags=["orders"])


def order_to_response(order: dict) -> dict:
    return {
        "id": str(order["_id"]),
        "items": [
            {"productId": item.get("productId"), "quantity": item.get("quantity")}
            for item in order.get("items", [])
        ],
        "total": order.get("total"),
        "createdAt": order.get("createdAt").isoformat() if order.get("createdAt") else None,
        "updatedAt": order.get("updatedAt").isoformat() if order.get("updatedAt") else None,
    }


async def calculate_total(items: list) -> float:
    total = 0.0
    for item in items:
        product_id = item.get("productId")
        quantity = item.get("quantity")
        if not product_id or quantity is None or not ObjectId.is_valid(product_id):
            continue
        product = await products_collection.find_one({"_id": ObjectId(product_id)})
        if product and product.get("price") is not None:
            total += product["price"] * quantity
    return round(total, 2)


def normalize_items(request: OrderRequest) -> list:
    if not request.items:
        return []
    return [{"productId": item.productId, "quantity": item.quantity} for item in request.items]


@router.get("")
async def get_all_orders(current_user: dict = Depends(get_current_user)):
    orders = []
    cursor = orders_collection.find()
    async for order in cursor:
        orders.append(order_to_response(order))
    return orders


@router.get("/{order_id}")
async def get_order_by_id(order_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return order_to_response(order)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(request: OrderRequest, current_user: dict = Depends(get_current_user)):
    items = normalize_items(request)
    total = await calculate_total(items)
    now = datetime.utcnow()
    order_doc = {
        "items": items,
        "total": total,
        "createdAt": now,
        "updatedAt": now,
    }
    result = await orders_collection.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id
    return order_to_response(order_doc)


@router.put("/{order_id}")
async def update_order(order_id: str, request: OrderRequest, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    existing = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    update_fields: dict = {"updatedAt": datetime.utcnow()}
    if request.items is not None:
        items = normalize_items(request)
        update_fields["items"] = items
        update_fields["total"] = await calculate_total(items)

    await orders_collection.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": update_fields},
    )

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return order_to_response(order)


@router.delete("/{order_id}")
async def delete_order(order_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    result = await orders_collection.delete_one({"_id": ObjectId(order_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return {"message": "Order deleted"}
