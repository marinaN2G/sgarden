import re
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from models.product import ProductRequest, ProductResponse
from database import products_collection
from security.jwt_handler import get_current_user
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/api/products", tags=["products"])

VALID_CATEGORIES = {"Electronics", "Accessories", "Storage", "Networking"}


def validate_product_request(request: ProductRequest, is_create: bool) -> dict:
    errors: dict = {}

    if is_create:
        if request.name is None or not request.name.strip():
            errors["name"] = "name is required and must be a non-empty string"
    elif request.name is not None and not request.name.strip():
        errors["name"] = "name must be a non-empty string"

    if request.price is not None and request.price <= 0:
        errors["price"] = "price must be a positive number"

    if request.category is not None and request.category not in VALID_CATEGORIES:
        errors["category"] = (
            "category must be one of: Electronics, Accessories, Storage, Networking"
        )

    return errors

# CODE QUALITY ISSUE: unused variable
service_name = "ProductService"


def product_to_response(product: dict) -> dict:
    """Convert MongoDB document to API response format."""
    return {
        "id": str(product["_id"]),
        "name": product.get("name"),
        "description": product.get("description"),
        "category": product.get("category"),
        "price": product.get("price"),
        "stock": product.get("stock", 0),
        "createdAt": product.get("createdAt", "").isoformat() if product.get("createdAt") else None,
        "updatedAt": product.get("updatedAt", "").isoformat() if product.get("updatedAt") else None,
    }


def format_product(product: dict) -> dict:
    """CODE QUALITY ISSUE: duplicate of product_to_response above."""
    return {
        "id": str(product["_id"]),
        "name": product.get("name"),
        "description": product.get("description"),
        "category": product.get("category"),
        "price": product.get("price"),
        "stock": product.get("stock", 0),
        "createdAt": product.get("createdAt", "").isoformat() if product.get("createdAt") else None,
        "updatedAt": product.get("updatedAt", "").isoformat() if product.get("updatedAt") else None,
    }


@router.get("")
async def get_all_products(
    page: int = 1,
    limit: int = 20,
    sort: Optional[str] = None,
    order: str = "asc",
):
    print("Fetching all products")
    safe_page = max(1, page)
    safe_limit = max(1, limit)

    total = await products_collection.count_documents({})

    cursor = products_collection.find()
    if sort:
        direction = -1 if order.lower() == "desc" else 1
        cursor = cursor.sort(sort, direction)
    cursor = cursor.skip((safe_page - 1) * safe_limit).limit(safe_limit)

    data = []
    async for product in cursor:
        data.append(product_to_response(product))

    return {
        "data": data,
        "page": safe_page,
        "limit": safe_limit,
        "total": total,
    }


@router.get("/stats")
async def get_product_stats():
    total_count = 0
    prices: list[float] = []
    category_count: dict[str, int] = {}

    cursor = products_collection.find()
    async for product in cursor:
        total_count += 1
        price = product.get("price")
        if price is not None:
            prices.append(price)
        category = product.get("category")
        if category is not None:
            category_count[category] = category_count.get(category, 0) + 1

    if prices:
        average_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
    else:
        average_price = 0.0
        min_price = None
        max_price = None

    return {
        "totalCount": total_count,
        "averagePrice": average_price,
        "minPrice": min_price,
        "maxPrice": max_price,
        "categoryCount": category_count,
    }


@router.get("/search")
async def search_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    minPrice: Optional[float] = None,
    maxPrice: Optional[float] = None,
):
    filters: list[dict] = []

    if q is not None and q.strip():
        pattern = re.escape(q)
        filters.append({
            "$or": [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"description": {"$regex": pattern, "$options": "i"}},
            ]
        })
    if category is not None and category.strip():
        filters.append({"category": category})

    price_range: dict = {}
    if minPrice is not None:
        price_range["$gte"] = minPrice
    if maxPrice is not None:
        price_range["$lte"] = maxPrice
    if price_range:
        filters.append({"price": price_range})

    query = {"$and": filters} if filters else {}

    products = []
    cursor = products_collection.find(query)
    async for product in cursor:
        products.append(product_to_response(product))
    return products


@router.get("/{product_id}")
async def get_product_by_id(product_id: str):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return product_to_response(product)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(request: ProductRequest, current_user: dict = Depends(get_current_user)):
    errors = validate_product_request(request, is_create=True)
    if errors:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Validation failed", "errors": errors},
        )

    product_doc = {
        "name": request.name,
        "description": request.description,
        "category": request.category,
        "price": request.price,
        "stock": request.stock if request.stock is not None else 0,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }

    result = await products_collection.insert_one(product_doc)
    product_doc["_id"] = result.inserted_id
    print(f"Created product: {request.name}")
    return product_to_response(product_doc)


async def update_product_legacy(product_id: str, request: ProductRequest, current_user: dict = Depends(get_current_user)):
    """CODE QUALITY ISSUE: duplicate of update_product."""
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    update_fields = {}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.description is not None:
        update_fields["description"] = request.description
    if request.category is not None:
        update_fields["category"] = request.category
    if request.price is not None:
        update_fields["price"] = request.price
    if request.stock is not None:
        update_fields["stock"] = request.stock

    if not update_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    update_fields["updatedAt"] = datetime.utcnow()

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": update_fields},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.put("/{product_id}")
async def update_product(product_id: str, request: ProductRequest, current_user: dict = Depends(get_current_user)):
    errors = validate_product_request(request, is_create=False)
    if errors:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Validation failed", "errors": errors},
        )

    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    update_fields = {}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.description is not None:
        update_fields["description"] = request.description
    if request.category is not None:
        update_fields["category"] = request.category
    if request.price is not None:
        update_fields["price"] = request.price
    if request.stock is not None:
        update_fields["stock"] = request.stock

    if not update_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    update_fields["updatedAt"] = datetime.utcnow()

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": update_fields},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.patch("/{product_id}/stock")
async def update_stock(product_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    if "stock" not in body or body.get("stock") is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "stock is required"},
        )
    stock = body.get("stock")
    if not isinstance(stock, int) or isinstance(stock, bool):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "stock must be an integer"},
        )
    if stock < 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "stock must be a non-negative integer"},
        )

    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"stock": stock, "updatedAt": datetime.utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.delete("/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await products_collection.delete_one({"_id": ObjectId(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return {"message": "Product deleted"}
