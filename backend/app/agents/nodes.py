"""LangGraph 节点实现（PDR §5）。

Intake / Matching / Chat / Verification / Coordinator(路由)。
"""

from __future__ import annotations

import uuid

from app.agents.state import AgentState, Intent
from app.agents.tools import classify_intent, embed_item, parse_item
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Item, ItemImage, ItemStatus, ItemType, MatchStatus
from app.db.session import SessionLocal
from app.services.llm import get_llm
from app.services.matching import find_and_store_matches

logger = get_logger(__name__)


# ─────────────────────────── 路由 / 协调 ───────────────────────────


async def classify_node(state: AgentState) -> AgentState:
    """Coordinator：意图识别。"""
    intent = await classify_intent(get_llm(), state.get("message", ""))
    logger.info("意图识别: %s", intent)
    return {"intent": intent}


def route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", Intent.other.value)
    if intent == Intent.report.value:
        return "intake"
    if intent == Intent.claim.value:
        return "verify"
    if intent == Intent.query.value:
        return "chat"
    return "chat"


# ─────────────────────────── Intake ───────────────────────────


async def intake_node(state: AgentState) -> AgentState:
    """解析登记内容，落库并生成向量。"""
    llm = get_llm()
    parsed = await parse_item(llm, state.get("message", ""), state.get("image_urls"))
    item_type = ItemType(state.get("item_type", ItemType.lost.value))

    item = Item(
        id=uuid.uuid4(),
        type=item_type,
        reporter_id=uuid.UUID(state["user_id"]) if state.get("user_id") else uuid.uuid4(),
        title=(parsed.get("title") or state.get("message", "")[:60]) or "未命名物品",
        description=state.get("message"),
        category=parsed.get("category") or None,
        brand=parsed.get("brand") or None,
        color=parsed.get("color") or None,
        material=parsed.get("material") or None,
        location_tag=parsed.get("location_tag") or None,
        distinguishing_features=parsed.get("distinguishing_features") or None,
        status=ItemStatus.active,
    )
    captions = [parsed["caption"]] if parsed.get("caption") else []
    item.embedding = await embed_item(item, captions)

    async with SessionLocal() as session:
        session.add(item)
        for url in state.get("image_urls", []):
            session.add(ItemImage(item_id=item.id, url=url, caption=parsed.get("caption")))
        await session.flush()
        matches = await find_and_store_matches(session, item)
        await session.commit()
        match_dicts = [
            {
                "id": str(m.id),
                "lost_item_id": str(m.lost_item_id),
                "found_item_id": str(m.found_item_id),
                "score": m.score,
                "reason": m.reason,
            }
            for m in matches
        ]

    reply = (
        f"已登记「{item.title}」，找到 {len(match_dicts)} 个高置信候选匹配。"
        if match_dicts
        else f"已登记「{item.title}」，暂未找到匹配，进入待匹配池，有新招领时会通知你。"
    )
    return {
        "parsed": parsed,
        "item_id": str(item.id),
        "matches": match_dicts,
        "status": "reported",
        "reply": reply,
    }


# ─────────────────────────── Matching（复审） ───────────────────────────


async def matching_node(state: AgentState) -> AgentState:
    """对已有 item 重新召回 + 重排（由后台/复检触发）。"""
    if not state.get("item_id"):
        return {"status": "no_item"}
    async with SessionLocal() as session:
        item = await session.get(Item, uuid.UUID(state["item_id"]))
        if item is None:
            return {"status": "not_found"}
        matches = await find_and_store_matches(session, item)
        await session.commit()
        match_dicts = [{"id": str(m.id), "score": m.score, "reason": m.reason} for m in matches]
    return {"matches": match_dicts, "status": "matched"}


# ─────────────────────────── Verification ───────────────────────────


async def verify_node(state: AgentState) -> AgentState:
    """核验问答（PDR §5.4）。骨架：生成核验问题 / 判定回答。

    生产实现：基于物品非公开细节生成问题，收集回答后由 deepseek-flash 判定置信度，
    低置信/高风险 => escalate_to_human（LangGraph interrupt）。
    """
    llm = get_llm()
    verification = state.get("verification") or {}
    item_id = state.get("item_id")

    if not verification.get("questions"):
        questions = await _generate_questions(llm, item_id)
        verification["questions"] = questions
        reply = "为确认所有权，请回答：" + " / ".join(questions)
        status = "verifying"
    else:
        from app.schemas.claim import VerificationResult  # noqa: F401

        result = await _judge_answers(llm, verification)
        verification["result"] = result
        status = "disputed" if result["risk_level"] == "high" else "passed"
        reply = result["judgement"]

    return {"verification": verification, "status": status, "reply": reply}


_QUESTIONS_SYSTEM = (
    "根据物品的非公开细节，生成 2 个只有真正失主能答的问题。"
    '只输出 JSON: {"questions": ["...", "..."]}'
)

_JUDGE_SYSTEM = (
    "判断认领者回答是否与失主一致。"
    '只输出 JSON: {"passed": bool, "confidence": 0~1, '
    '"risk_level": "low|medium|high", "judgement": "理由"}'
)


async def _generate_questions(llm, item_id: str | None) -> list[str]:  # noqa: ANN001
    data = await llm.complete_json(
        [
            {"role": "system", "content": _QUESTIONS_SYSTEM},
            {
                "role": "user",
                "content": f"物品ID: {item_id or '未知'}（生产环境应注入物品非公开字段）",
            },
        ],
        thinking=False,
    )
    return list(data.get("questions") or ["请描述物品的独特特征", "物品内/背面有什么标记？"])


async def _judge_answers(llm, verification: dict) -> dict:  # noqa: ANN001
    data = await llm.complete_json(
        [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": str(verification)},
        ],
        thinking=True,
    )
    return {
        "passed": bool(data.get("passed", False)),
        "confidence": float(data.get("confidence", 0.0)),
        "risk_level": str(data.get("risk_level", "medium")),
        "judgement": str(data.get("judgement", "")),
    }


# ─────────────────────────── Chat ───────────────────────────


_CHAT_SYSTEM = """你是校园失物招领助手的对话入口。回答要简洁、友好、中文。
若用户想登记失物/招领，引导其描述物品并上传照片；若要认领，引导其发起认领并接受核验。"""


async def chat_node(state: AgentState) -> AgentState:
    llm = get_llm()
    messages = [{"role": "system", "content": _CHAT_SYSTEM}]
    messages.append({"role": "user", "content": state.get("message", "")})
    reply = await llm.complete(messages, thinking=False)
    return {"reply": reply, "status": "answered", "matches": state.get("matches", [])}


async def finish_node(state: AgentState) -> AgentState:
    return {"status": state.get("status", "done")}


def match_status_of(score: float) -> MatchStatus:
    return MatchStatus.confirmed if score >= settings.match_high_threshold else MatchStatus.pending
