"""路径定位、复核申请和一致性核对联动接口。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.path_review import path_review_service as service

router = APIRouter(prefix="/api", tags=["路径定位与复核"])


class NodePayload(BaseModel):
    id: str | None = None
    name: str
    parent_id: str | None = None
    kind: str | None = None
    code: str | None = None
    gap: bool = False
    gap_reason: str | None = None


class MovePayload(BaseModel):
    new_parent_id: str | None = None
    target_parent_id: str | None = None
    parent_id: str | None = None


class ReviewPayload(BaseModel):
    node_id: str
    note: str = ""
    draft_note: str = ""
    client_ref: str | None = None
    assignee: str | None = None
    auto_claim: bool = False


class DraftPayload(BaseModel):
    note: str = ""


class ClaimPayload(BaseModel):
    assignee: str = "复核人"


class CompletePayload(BaseModel):
    mode: str | None = "original"
    note: str | None = ""
    completion_note: str | None = ""
    result: str | None = "确认一致"


@router.get("/path-locator/tree")
def get_tree() -> dict[str, Any]:
    return {"items": service.tree(), "nodes": service.list_nodes()}


@router.get("/path-locator/nodes")
def get_nodes() -> dict[str, Any]:
    return {"items": service.list_nodes(), "total": len(service.nodes)}


@router.get("/path-locator/candidates")
def get_candidates(
    name: str = "", parent_id: str = "", gap_only: bool = False,
) -> dict[str, Any]:
    items = service.candidates(name=name, parent_id=parent_id, gap_only=gap_only)
    return {"items": items, "total": len(items)}


@router.post("/path-locator/nodes")
def create_node(payload: NodePayload) -> dict[str, Any]:
    ok, message, node = service.create_node(payload.model_dump())
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "entry": node}


@router.post("/path-locator/nodes/{node_id}/move")
def move_node(node_id: str, payload: MovePayload) -> dict[str, Any]:
    new_parent = payload.new_parent_id or payload.target_parent_id or payload.parent_id
    ok, message, result = service.move_node(node_id, new_parent)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": ok, "message": message, "entry": result}


@router.get("/path-reviews")
def list_reviews() -> dict[str, Any]:
    items = service.list_reviews()
    return {"items": items, "total": len(items)}


@router.get("/path-reviews/by-client-ref/{client_ref}")
def get_by_client_ref(client_ref: str) -> dict[str, Any]:
    review = service.find_by_client_ref(client_ref)
    if review is None:
        raise HTTPException(status_code=404, detail="未找到对应申请")
    return {"ok": True, "entry": review}


@router.get("/path-reviews/{review_id}")
def get_review(review_id: str) -> dict[str, Any]:
    review = service.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"复核申请 {review_id} 不存在")
    return {"ok": True, "entry": review}


@router.post("/path-reviews")
def create_review(payload: ReviewPayload) -> dict[str, Any]:
    data = payload.model_dump()
    if not data.get("note"):
        data["note"] = data.get("draft_note", "")
    ok, message, review = service.create_review(data)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "entry": review}


@router.patch("/path-reviews/{review_id}")
def save_draft(review_id: str, payload: DraftPayload) -> dict[str, Any]:
    ok, message, review = service.save_draft(review_id, payload.note)
    if not ok:
        raise HTTPException(status_code=404, detail=message)
    return {"ok": True, "message": message, "entry": review}


@router.post("/path-reviews/{review_id}/claim")
def claim_review(review_id: str, payload: ClaimPayload | None = None) -> dict[str, Any]:
    assignee = payload.assignee if payload else "复核人"
    ok, message, review = service.claim_review(review_id, assignee)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": ok, "message": message, "entry": review}


@router.post("/path-reviews/{review_id}/sign", include_in_schema=False)
def sign_review_alias(review_id: str, payload: ClaimPayload | None = None) -> dict[str, Any]:
    return claim_review(review_id, payload)


@router.post("/path-reviews/{review_id}/relink")
def relink_review(review_id: str) -> dict[str, Any]:
    ok, message, review = service.relink_review(review_id)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": ok, "message": message, "entry": review}


@router.post("/path-reviews/{review_id}/complete")
def complete_review(review_id: str, payload: CompletePayload | None = None) -> dict[str, Any]:
    ok, message, review = service.complete_review(
        review_id, payload.model_dump() if payload else {},
    )
    if not ok:
        raise HTTPException(
            status_code=409,
            detail={"message": message, "entry": review},
        )
    return {"ok": ok, "message": message, "entry": review}


@router.post("/path-reviews/{review_id}/finish", include_in_schema=False)
def finish_review_alias(review_id: str, payload: CompletePayload | None = None) -> dict[str, Any]:
    return complete_review(review_id, payload)


# 下划线/连字符两套别名，兼容不同调用方对 hier_path 模块路径的直觉。
@router.get("/hier_path/locator/tree", include_in_schema=False)
def alias_hier_tree_underscore() -> dict[str, Any]:
    return get_tree()


@router.get("/hier-path/locator/tree", include_in_schema=False)
def alias_hier_tree_hyphen() -> dict[str, Any]:
    return get_tree()


@router.get("/hier_path/reviews", include_in_schema=False)
def alias_hier_reviews_underscore() -> dict[str, Any]:
    return list_reviews()


@router.get("/hier-path/reviews", include_in_schema=False)
def alias_hier_reviews_hyphen() -> dict[str, Any]:
    return list_reviews()


@router.post("/hier_path/reviews", include_in_schema=False)
def alias_create_hier_review_underscore(payload: ReviewPayload) -> dict[str, Any]:
    return create_review(payload)


@router.post("/hier-path/reviews", include_in_schema=False)
def alias_create_hier_review_hyphen(payload: ReviewPayload) -> dict[str, Any]:
    return create_review(payload)


@router.post("/hier_path/nodes/{node_id}/move", include_in_schema=False)
def alias_move_hier_node_underscore(node_id: str, payload: MovePayload) -> dict[str, Any]:
    return move_node(node_id, payload)


@router.post("/hier-path/nodes/{node_id}/move", include_in_schema=False)
def alias_move_hier_node_hyphen(node_id: str, payload: MovePayload) -> dict[str, Any]:
    return move_node(node_id, payload)
