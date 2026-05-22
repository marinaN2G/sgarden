from pydantic import BaseModel
from typing import List, Optional


class OrderItemRequest(BaseModel):
    productId: str
    quantity: int


class OrderRequest(BaseModel):
    items: Optional[List[OrderItemRequest]] = None
