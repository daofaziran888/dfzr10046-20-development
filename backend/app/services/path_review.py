"""层级路径定位与一致性复核申请的内存领域服务。

这里维护两类强相关对象：

* ``hier_node``：带稳定 ID 的地区树。同名地区可以挂在不同父节点下，因此
  任何定位、草稿和申请都必须以节点 ID 为准，不能只按地区名称匹配。
* ``path_review``：从层级路径页发起的复核申请。申请保存提交时的路径快照，
  父节点之后被移动时，页面仍可同时展示“那次提交的路径”和“当前路径”。

申请创建时会向 ``conform_check`` 表写入一条“待核对”记录，使层级路径页的
操作立即成为一致性核对工作台中的待办。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.store import store


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_nodes() -> list[dict[str, Any]]:
    # 节点 ID 与名称分离：两个“朝阳区”分别属于北京市和长春市。
    return [
        {"id": "root-cn", "name": "全国", "parent_id": None, "kind": "root",
         "code": "CN", "gap": False},
        {"id": "region-huabei", "name": "华北区", "parent_id": "root-cn",
         "kind": "region-group", "code": "HB", "gap": False},
        {"id": "city-beijing", "name": "北京市", "parent_id": "region-huabei",
         "kind": "parent", "code": "BJ", "gap": False},
        {"id": "chaoyang-bj", "name": "朝阳区", "parent_id": "city-beijing",
         "kind": "district", "code": "110105", "gap": True,
         "gap_reason": "GIS 边界版本与客户地址口径存在 3 个待核键"},
        {"id": "haidian-bj", "name": "海淀区", "parent_id": "city-beijing",
         "kind": "district", "code": "110108", "gap": True,
         "gap_reason": "园区编码与行政区划编码粒度不一致"},
        {"id": "region-dongbei", "name": "东北区", "parent_id": "root-cn",
         "kind": "region-group", "code": "DB", "gap": False},
        {"id": "city-changchun", "name": "长春市", "parent_id": "region-dongbei",
         "kind": "parent", "code": "CC", "gap": False},
        {"id": "chaoyang-cc", "name": "朝阳区", "parent_id": "city-changchun",
         "kind": "district", "code": "220104", "gap": True,
         "gap_reason": "与北京市朝阳区同名，但父节点和统计编码均不同"},
        {"id": "region-huadong", "name": "华东区", "parent_id": "root-cn",
         "kind": "region-group", "code": "HD", "gap": False},
        {"id": "city-hangzhou", "name": "杭州市", "parent_id": "region-huadong",
         "kind": "parent", "code": "HZ", "gap": False},
        {"id": "xihu-hz", "name": "西湖区", "parent_id": "city-hangzhou",
         "kind": "district", "code": "330106", "gap": True,
         "gap_reason": "景区托管区域与民政区划覆盖范围不同"},
        {"id": "city-nanchang", "name": "南昌市", "parent_id": "region-huadong",
         "kind": "parent", "code": "NC", "gap": False},
        {"id": "xihu-nc", "name": "西湖区", "parent_id": "city-nanchang",
         "kind": "district", "code": "360103", "gap": False,
         "gap_reason": ""},
        {"id": "relocated-parent", "name": "迁移托管区", "parent_id": "root-cn",
         "kind": "parent", "code": "RELOC", "gap": False,
         "description": "父节点变更后的默认托管位置"},
    ]


class PathReviewService:
    """路径树、检索定位和复核申请工作流。"""

    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = _default_nodes()
        self.reviews: list[dict[str, Any]] = []
        # 通用 hier_path 记录按“上级层级名称”建关系；移动后用显式 ID 覆盖，
        # 避免两个同名父节点导致重新解析到错误分支。
        self.parent_overrides: dict[str, str] = {}

    # ------------------------------------------------------------------
    # 节点树与检索
    # ------------------------------------------------------------------
    def _merged_nodes(self) -> list[dict[str, Any]]:
        """合并内置地区树与通过通用“登记层级路径”写入的记录。"""
        nodes: list[dict[str, Any]] = [dict(node) for node in self.nodes]
        used_ids = {str(node["id"]) for node in nodes}

        for row in store.rows("hier_path"):
            row_id = row.get("id")
            mapped_id = f"hier-row-{row_id}"
            if mapped_id in used_ids:
                continue
            name = str(row.get("层级名称") or "").strip()
            if not name:
                continue
            parent_name = str(row.get("上级层级") or "").strip()
            dimension = str(row.get("所属维度") or "区域维度")

            # 种子中的“全国 / NONE”与内置树根是同一个节点，复用稳定 ID。
            if parent_name.upper() in {"", "NONE"} and name == "全国":
                root = next((node for node in nodes if node.get("name") == "全国"), None)
                if root is not None:
                    root["row_id"] = row_id
                    root["path_code"] = row.get("路径编号")
                    continue

            node: dict[str, Any] = {
                "id": mapped_id,
                "row_id": row_id,
                "name": name,
                "parent_id": None,
                "parent_name_raw": parent_name,
                "dimension": dimension,
                "code": str(row.get("路径编号") or ""),
                "kind": "hier-path-row",
                "gap": bool(row.get("abnormal") or row.get("status") == "存在断裂"),
                "gap_reason": str(row.get("跨越标记") or ""),
                "status": row.get("status"),
            }
            nodes.append(node)
            used_ids.add(mapped_id)

        ids = {str(node["id"]) for node in nodes}
        by_name: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for node in nodes:
            if not node.get("dimension"):
                node["dimension"] = "区域维度"
            key = (str(node["dimension"]), str(node["name"]))
            by_name.setdefault(key, []).append(node)

        for node in nodes:
            node_id = str(node["id"])
            if node_id in self.parent_overrides:
                node["parent_id"] = self.parent_overrides[node_id]
                continue
            # 内置节点已经有明确 parent_id；只有通用行需要按名称解析。
            if "parent_name_raw" not in node:
                continue

            parent_name = str(node.get("parent_name_raw") or "").strip()
            if not parent_name or parent_name.upper() == "NONE":
                node["parent_id"] = "root-cn" if "root-cn" in ids and node_id != "root-cn" else None
                continue

            dimension = str(node.get("dimension") or "区域维度")
            matches = by_name.get((dimension, parent_name), [])
            parent = next((item for item in matches if item["id"] != node_id), None)
            if parent is None:
                virtual_id = f"missing-parent:{dimension}:{parent_name}"
                if virtual_id not in ids:
                    nodes.append({
                        "id": virtual_id,
                        "name": parent_name,
                        "parent_id": "root-cn" if "root-cn" in ids else None,
                        "dimension": dimension,
                        "kind": "missing-parent",
                        "gap": True,
                        "gap_reason": "上级层级不存在",
                    })
                    ids.add(virtual_id)
                node["parent_id"] = virtual_id
            else:
                node["parent_id"] = str(parent["id"])

        return nodes

    def list_nodes(self) -> list[dict[str, Any]]:
        return self._merged_nodes()

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return next((node for node in self._merged_nodes() if node["id"] == node_id), None)

    def _raw_builtin_node(self, node_id: str) -> dict[str, Any] | None:
        return next((node for node in self.nodes if node["id"] == node_id), None)

    def _generic_row(self, row_id: Any) -> dict[str, Any] | None:
        if row_id is None:
            return None
        return store.find("hier_path", int(row_id))

    def _path_nodes(self, node_id: str) -> list[dict[str, Any]]:
        path: list[dict[str, Any]] = []
        current = self.get_node(node_id)
        guard = 0
        while current is not None and guard < 100:
            path.append({"id": current["id"], "name": current["name"]})
            parent_id = current.get("parent_id")
            if not parent_id:
                break
            current = self.get_node(str(parent_id))
            guard += 1
        path.reverse()
        return path

    def path_text(self, node_id: str) -> str:
        return " / ".join(item["name"] for item in self._path_nodes(node_id))

    def _descendant_ids(self, root_id: str) -> set[str]:
        result = {root_id}
        changed = True
        all_nodes = self._merged_nodes()
        while changed:
            changed = False
            for node in all_nodes:
                parent_id = str(node.get("parent_id") or "")
                if parent_id in result and node["id"] not in result:
                    result.add(node["id"])
                    changed = True
        return result

    def tree(self) -> list[dict[str, Any]]:
        all_nodes = self._merged_nodes()
        nodes = {node["id"]: {**dict(node), "children": []} for node in all_nodes}
        roots: list[dict[str, Any]] = []
        for node in nodes.values():
            parent_id = node.get("parent_id")
            if parent_id and parent_id in nodes:
                nodes[parent_id]["children"].append(node)
            else:
                roots.append(node)
        return roots

    def candidates(
        self, name: str = "", parent_id: str = "", gap_only: bool = False,
    ) -> list[dict[str, Any]]:
        """按名称检索；给定 parent_id 时只在该父节点子树内筛选。

        同名节点不会被合并：每条候选都带稳定 id、父节点 id 和完整路径。
        """
        keyword = (name or "").strip().casefold()
        allowed: set[str] | None = None
        if parent_id:
            parent = self.get_node(parent_id)
            if parent is None:
                return []
            allowed = self._descendant_ids(parent_id)

        items: list[dict[str, Any]] = []
        for node in self._merged_nodes():
            if allowed is not None and node["id"] not in allowed:
                continue
            if gap_only and not node.get("gap"):
                continue
            if keyword and keyword not in str(node["name"]).casefold() \
                    and keyword not in str(node.get("code", "")).casefold():
                continue
            path = self._path_nodes(node["id"])
            items.append({
                **dict(node),
                "path": path,
                "path_text": " / ".join(item["name"] for item in path),
                "parent_name": next(
                    (item["name"] for item in path[:-1] if item["id"] == node.get("parent_id")),
                    path[-2]["name"] if len(path) > 1 else "",
                ),
            })
        return items

    def create_node(self, payload: dict[str, Any]) -> tuple[bool, str, dict[str, Any] | None]:
        name = str(payload.get("name") or "").strip()
        if not name:
            return False, "节点名称不能为空", None
        node_id = str(payload.get("id") or f"node-{uuid4().hex[:10]}")
        if self.get_node(node_id) is not None:
            return False, f"节点 ID 已存在：{node_id}", None
        parent_id = str(payload.get("parent_id") or "") or None
        if parent_id and self.get_node(parent_id) is None:
            return False, f"父节点不存在：{parent_id}", None
        node = {
            "id": node_id,
            "name": name,
            "parent_id": parent_id,
            "kind": str(payload.get("kind") or "district"),
            "code": str(payload.get("code") or ""),
            "gap": bool(payload.get("gap", False)),
            "gap_reason": str(payload.get("gap_reason") or ""),
        }
        self.nodes.append(node)
        return True, f"节点 {name} 已加入路径树", node

    def move_node(
        self, node_id: str, new_parent_id: str | None = None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        node = self.get_node(node_id)
        if node is None:
            return False, f"路径节点 {node_id} 不存在", None
        if not new_parent_id:
            new_parent_id = "relocated-parent"
        if new_parent_id == node_id:
            return False, "不能把节点移动到自身下面", None
        target = self.get_node(new_parent_id)
        if target is None:
            return False, f"新父节点不存在：{new_parent_id}", None
        # 只禁止把当前节点挂到它自己的后代下面；移到更高祖先或其他分支是允许的。
        if new_parent_id in self._descendant_ids(node_id):
            return False, "不能把父节点移动到它自己的后代节点下", None

        old_parent_id = node.get("parent_id")
        old_path = self.path_text(node_id)

        raw_builtin = self._raw_builtin_node(node_id)
        if raw_builtin is not None:
            raw_builtin["parent_id"] = new_parent_id
            raw_builtin["last_moved_at"] = _now()
            raw_builtin["previous_parent_id"] = old_parent_id
        elif node.get("row_id") is not None:
            row = self._generic_row(node.get("row_id"))
            if row is not None:
                # 通用层级记录用上级名称表达关系；同时保存 ID 覆盖以避免同名歧义。
                row["上级层级"] = target["name"]
                row["last_moved_at"] = _now()
            self.parent_overrides[node_id] = new_parent_id
        else:
            # 虚拟断裂父节点等对象没有原始表行；用覆盖关系保存本次移动。
            self.parent_overrides[node_id] = new_parent_id

        new_path = self.path_text(node_id)

        # 路径变化会影响所有未办结申请；读取申请时也会动态计算，这里保留事件。
        for review in self.reviews:
            if review["node_id"] in self._descendant_ids(node_id) or review["node_id"] == node_id:
                review.setdefault("path_events", []).append({
                    "at": _now(),
                    "moved_node_id": node_id,
                    "old_path": old_path,
                    "new_path": new_path,
                })

        return True, f"已将 {node['name']} 从 {old_path} 移至 {new_path}", {
            "node": node, "old_path": old_path, "new_path": new_path,
        }

    # ------------------------------------------------------------------
    # 复核申请
    # ------------------------------------------------------------------
    def _seed_reviews(self) -> None:
        """放一条已签收申请，便于直接验证父节点变更后的办理范围冲突。"""
        ok, _, review = self.create_review({
            "node_id": "haidian-bj",
            "note": "海淀园区与行政区划口径需要在改挂演练前先核对。",
            "client_ref": "seed-haidian-claimed",
            "auto_claim": True,
        })
        if ok and review:
            review["id"] = 1
            review["code"] = "PR-001"

    def _next_review_id(self) -> int:
        return max((int(item.get("id", 0)) for item in self.reviews), default=0) + 1

    def _decorate_review(self, review: dict[str, Any]) -> dict[str, Any]:
        node_id = str(review["node_id"])
        current_node = self.get_node(node_id)
        current_path = self._path_nodes(node_id) if current_node else []
        current_path_text = " / ".join(item["name"] for item in current_path)
        submitted_path = review.get("submitted_path") or []
        submitted_ids = [item["id"] for item in submitted_path]
        current_ids = [item["id"] for item in current_path]
        path_changed = bool(current_path) and submitted_ids != current_ids
        submitted_parent_id = review.get("submitted_parent_id")
        scope_ids = set(review.get("scope_node_ids") or [])
        original_scope_intact = bool(current_node and (
            not submitted_parent_id
            or node_id in self._descendant_ids(str(submitted_parent_id))
        ))
        # scope_ids 是提交时快照；若父节点整体移动，稳定 ID 仍在同一子树中。
        target_in_snapshot_scope = node_id in scope_ids if scope_ids else True
        conflict = path_changed and review.get("status") in {"待签收", "已签收", "处理中", "已改挂"}
        signed = review.get("status") in {"已签收", "处理中", "已改挂"}
        can_complete_original = (
            review.get("status") != "已办结"
            and signed
            and original_scope_intact
            and target_in_snapshot_scope
        )
        must_relink = conflict and not original_scope_intact
        if review.get("status") == "已办结":
            guidance = "该申请已办结；以下同时保留提交路径、办理路径和当前路径。"
        elif must_relink:
            guidance = (
                "当前地区已离开原父节点子树，原办理范围不再包含该地区；"
                "须改挂新路径后才能办结。"
            )
        elif path_changed and signed:
            guidance = (
                "该申请已签收且原父节点子树仍完整，签收时锁定的原办理范围继续有效；"
                "现在可以沿原范围办结，也可以改挂当前新路径后办结。"
            )
        elif path_changed:
            guidance = "路径已变更；申请尚未签收，请按当前路径核对后签收，或先改挂新路径。"
        else:
            guidance = "路径未变更，可正常签收并办结。"

        return {
            **review,
            "current_path": current_path,
            "current_path_text": current_path_text or "节点已不存在",
            "current_parent_id": current_node.get("parent_id") if current_node else None,
            "path_changed": path_changed,
            "conflict": conflict,
            "original_scope_intact": original_scope_intact,
            "can_complete_original": can_complete_original,
            "must_relink": must_relink,
            "guidance": guidance,
            "return_route": f"/hier_path?review={review.get('id')}&node={node_id}",
            "workbench_route": f"/conform_check?review={review.get('id')}",
        }

    def list_reviews(self) -> list[dict[str, Any]]:
        return [self._decorate_review(review) for review in self.reviews]

    def get_review(self, review_id: int | str) -> dict[str, Any] | None:
        review = next(
            (item for item in self.reviews
             if str(item.get("id")) == str(review_id) or item.get("code") == str(review_id)),
            None,
        )
        return self._decorate_review(review) if review else None

    def find_by_client_ref(self, client_ref: str) -> dict[str, Any] | None:
        if not client_ref:
            return None
        review = next((item for item in self.reviews if item.get("client_ref") == client_ref), None)
        return self._decorate_review(review) if review else None

    def create_review(self, payload: dict[str, Any]) -> tuple[bool, str, dict[str, Any] | None]:
        node_id = str(payload.get("node_id") or "").strip()
        node = self.get_node(node_id)
        if node is None:
            return False, f"请先选择实际地区节点：{node_id}", None

        client_ref = str(payload.get("client_ref") or "").strip()
        existing = self.find_by_client_ref(client_ref) if client_ref else None
        if existing:
            return True, "同一申请正在提交，已返回原申请", existing

        note = str(payload.get("note") or payload.get("draft_note") or "").strip()
        path = self._path_nodes(node_id)
        parent_id = node.get("parent_id")
        scope_ids = sorted(self._descendant_ids(str(parent_id))) if parent_id else [node_id]
        review_id = self._next_review_id()
        code = str(payload.get("code") or f"PR-{review_id:03d}")
        while any(item.get("code") == code for item in self.reviews):
            review_id += 1
            code = f"PR-{review_id:03d}"

        conform_id = self._create_conform_todo(review_id, code, node, path, note)
        review = {
            "id": review_id,
            "code": code,
            "client_ref": client_ref or f"server-{uuid4().hex}",
            "node_id": node_id,
            "node_name": node["name"],
            "submitted_parent_id": parent_id,
            "submitted_parent_name": next(
                (item["name"] for item in path[:-1] if item["id"] == parent_id),
                path[-2]["name"] if len(path) > 1 else "",
            ),
            "submitted_path": path,
            "submitted_path_text": " / ".join(item["name"] for item in path),
            "scope_node_ids": scope_ids,
            "scope_label": f"原父节点 {parent_id} 的子树（{len(scope_ids)} 个稳定节点）",
            "note": note,
            "draft_note": note,
            "status": "待签收",
            "assignee": "",
            "conform_entry_id": conform_id,
            "conform_code": f"CC-{code}",
            "created_at": _now(),
            "claimed_at": "",
            "completed_at": "",
            "resolution_mode": "",
            "completion_note": "",
            "relinked": False,
            "path_events": [],
        }
        self.reviews.append(review)

        if payload.get("auto_claim"):
            self.claim_review(review_id, str(payload.get("assignee") or "复核人"))

        decorated = self.get_review(review_id)
        return True, f"已生成复核待办 {code}，并联动一致性核对 {review['conform_code']}", decorated

    def _create_conform_todo(
        self, review_id: int, code: str, node: dict[str, Any],
        path: list[dict[str, Any]], note: str,
    ) -> int:
        rows = store.rows("conform_check")
        entry_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        dimension = "区域维度"
        path_text = " / ".join(item["name"] for item in path)
        entry = {
            "id": entry_id,
            "status": "待核对",
            "pending": True,
            "abnormal": bool(node.get("gap")),
            "核对编号": f"CC-{code}",
            "基准维度": dimension,
            "对照维度": f"{dimension}@GIS",
            "核对粒度": f"地区：{path_text}",
            "匹配键数": "",
            "不匹配键数": "待复核",
            "核对结论": "待核对",
            "核对时间": "",
            "review_id": review_id,
            "review_code": code,
            "path_node_id": node["id"],
            "path_node_name": node["name"],
            "path_text": path_text,
            "review_note": note,
            "source_route": f"/hier_path?review={review_id}&node={node['id']}",
        }
        rows.append(entry)
        return entry_id

    def save_draft(self, review_id: int | str, note: str) -> tuple[bool, str, dict[str, Any] | None]:
        review = next((item for item in self.reviews if str(item["id"]) == str(review_id)), None)
        if review is None:
            return False, f"复核申请 {review_id} 不存在", None
        review["draft_note"] = note
        # 未正式提交说明前 note 与 draft_note 保持一致；已提交后草稿修改不覆盖正式说明。
        if review["status"] == "待签收" and not review.get("submitted_note"):
            review["note"] = note
        review["draft_saved_at"] = _now()
        return True, "说明草稿已保存", self.get_review(review_id)

    def claim_review(
        self, review_id: int | str, assignee: str = "复核人",
    ) -> tuple[bool, str, dict[str, Any] | None]:
        review = next((item for item in self.reviews if str(item["id"]) == str(review_id)), None)
        if review is None:
            return False, f"复核申请 {review_id} 不存在", None
        if review["status"] == "已办结":
            return False, "申请已办结，不能再签收", self.get_review(review_id)
        if review["status"] == "待签收":
            review["status"] = "已签收"
            review["assignee"] = assignee or "复核人"
            review["claimed_at"] = _now()
        return True, f"已由 {review['assignee']} 签收，原办理范围开始锁定", self.get_review(review_id)

    def relink_review(self, review_id: int | str) -> tuple[bool, str, dict[str, Any] | None]:
        review = next((item for item in self.reviews if str(item["id"]) == str(review_id)), None)
        if review is None:
            return False, f"复核申请 {review_id} 不存在", None
        decorated = self.get_review(review_id)
        if not decorated:
            return False, "申请状态读取失败", None
        if review["status"] == "已办结":
            return False, "申请已办结，不能重新挂接", decorated
        path = self._path_nodes(str(review["node_id"]))
        review["relinked"] = True
        review["relinked_at"] = _now()
        review["relinked_path"] = path
        review["relinked_path_text"] = " / ".join(item["name"] for item in path)
        review["resolution_mode"] = "relink"
        if review["status"] == "待签收":
            review["status"] = "已改挂"
        else:
            review["status"] = "已改挂"
        return True, "已改挂到当前新路径，现在可以办结", self.get_review(review_id)

    def complete_review(
        self, review_id: int | str, payload: dict[str, Any] | None = None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        payload = payload or {}
        review = next((item for item in self.reviews if str(item["id"]) == str(review_id)), None)
        if review is None:
            return False, f"复核申请 {review_id} 不存在", None
        decorated = self.get_review(review_id)
        if not decorated:
            return False, "申请状态读取失败", None
        if review["status"] == "已办结":
            return True, "申请此前已办结，未重复处理", decorated

        mode = str(payload.get("mode") or payload.get("scope_mode") or "original").strip()
        if mode in {"new", "current", "relink", "新路径", "改挂新路径"}:
            mode = "relink"
        elif mode in {"old", "snapshot", "original", "原范围", "沿原范围"}:
            mode = "original"

        if mode == "original" and decorated["path_changed"] and not decorated["original_scope_intact"]:
            return False, (
                "原父节点子树已不包含该地区，不能沿原范围办结；请先改挂新路径。"
            ), decorated

        completion_note = str(payload.get("completion_note") or payload.get("note") or "").strip()
        result = str(payload.get("result") or payload.get("conclusion") or "确认一致").strip()
        if review["status"] == "待签收":
            # 兼容未单独点签收的操作；显式签收后的范围锁定语义仍由 claim 接口保留。
            review["assignee"] = review.get("assignee") or "复核人"
            review["claimed_at"] = review.get("claimed_at") or _now()

        review["status"] = "已办结"
        review["completed_at"] = _now()
        review["completion_note"] = completion_note
        review["result"] = result
        review["resolution_mode"] = mode
        if mode == "relink":
            path = self._path_nodes(str(review["node_id"]))
            review["relinked"] = True
            review["relinked_path"] = path
            review["relinked_path_text"] = " / ".join(item["name"] for item in path)

        conform_id = review.get("conform_entry_id")
        conform_row = store.find("conform_check", int(conform_id)) if conform_id else None
        if conform_row is not None:
            passed = result not in {"登记偏差", "存在偏差", "不一致"}
            conform_row["status"] = "已一致" if passed else "存在偏差"
            conform_row["pending"] = False
            conform_row["abnormal"] = not passed
            conform_row["核对结论"] = "已一致" if passed else "存在偏差"
            conform_row["核对时间"] = _now()[:10]
            conform_row["复核说明"] = completion_note or review.get("note", "")
            conform_row["scope_mode"] = mode

        message = "已沿原办理范围办结" if mode == "original" else "已改挂新路径并办结"
        return True, message, self.get_review(review_id)


path_review_service = PathReviewService()
