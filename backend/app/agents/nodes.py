"""LangGraph 节点实现（PDR §5）。

Intake / Matching / Chat / Verification / Coordinator(路由)。
"""

from __future__ import annotations

import uuid

from langgraph.types import interrupt
from sqlalchemy import select

from app.agents.checkpointer import get_checkpointer
from app.agents.state import AgentState, Intent
from app.agents.tools import classify_intent, embed_item, parse_item
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Item, ItemImage, ItemStatus, ItemType, Match, MatchStatus
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


async def record_user_node(state: AgentState) -> AgentState:
    """把用户本轮消息写入会话历史（多轮记忆）。"""
    history = list(state.get("history") or [])
    message = state.get("message", "")
    if message:
        history.append({"role": "user", "content": message})
    return {"history": history}


def route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", Intent.other.value)
    if intent == Intent.report.value:
        return "intake"
    if intent == Intent.claim.value:
        return "review"
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


# ─────────────────────── Verification（严格服务端私密）───────────────────────

# 仅用于服务端核验比对，绝不通过 API 返回给认领者
_PRIVATE_FIELDS = (
    "title",
    "category",
    "brand",
    "color",
    "material",
    "description",
    "distinguishing_features",
)


def item_private_text(item: Item) -> str:
    """拼装物品的私密比对基准（仅服务端使用）。"""
    lines = []
    for field in _PRIVATE_FIELDS:
        value = getattr(item, field, None)
        if value:
            lines.append(f"{field}: {value}")
    return "\n".join(lines) or "（无更多细节）"


async def load_item(item_id: str | None) -> Item | None:
    if not item_id:
        return None
    async with SessionLocal() as session:
        return await session.get(Item, uuid.UUID(item_id))


_QUESTIONS_SYSTEM = (
    "你是失物招领的核验官。根据【物品真实信息】生成 2 个只有真正失主能答对的问题。\n"
    "严格要求：问题文本中【不得出现】任何真实信息的具体取值"
    "（例如不得写出颜色、品牌、内含物到底是什么），只能要求认领者主动描述。\n"
    '只输出 JSON: {"questions": ["...", "..."]}'
)

_JUDGE_SYSTEM = (
    "你是失物招领的核验官。依据【物品真实信息】判断认领者的回答是否与之一致。\n"
    "回答含糊、可被轻易猜中、或与真实信息冲突的，应判不通过并给高风险。\n"
    '只输出 JSON: {"passed": bool, "confidence": 0~1, '
    '"risk_level": "low|medium|high", "judgement": "理由"}'
)


async def generate_questions(llm, item: Item | None) -> list[str]:  # noqa: ANN001
    """基于物品私密信息生成核验问题（问题文本不泄露答案）。"""
    if item is None:
        return ["请描述该物品的独特特征", "物品内部或背面有什么标记？"]
    data = await llm.complete_json(
        [
            {"role": "system", "content": _QUESTIONS_SYSTEM},
            {"role": "user", "content": f"【物品真实信息】\n{item_private_text(item)}"},
        ],
        thinking=False,
    )
    return list(data.get("questions") or ["请描述该物品的独特特征", "物品内部或背面有什么标记？"])


async def judge_answers(llm, item: Item | None, answers: list[dict]) -> dict:  # noqa: ANN001
    """对照物品私密信息判定认领者回答。"""
    truth = item_private_text(item) if item else "（缺失，无法比对）"
    answer_text = "\n".join(f"Q: {a.get('question')}\nA: {a.get('answer')}" for a in answers)
    data = await llm.complete_json(
        [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {
                "role": "user",
                "content": f"【物品真实信息】\n{truth}\n\n【认领者回答】\n{answer_text}",
            },
        ],
        thinking=True,
    )
    return {
        "passed": bool(data.get("passed", False)),
        "confidence": float(data.get("confidence", 0.0)),
        "risk_level": str(data.get("risk_level", "medium")),
        "judgement": str(data.get("judgement", "")),
    }


async def verify_node(state: AgentState) -> AgentState:
    """核验问答（PDR §5.4）。基于物品私密信息生成问题 / 判定回答。"""
    llm = get_llm()
    verification = state.get("verification") or {}
    item = await load_item(state.get("item_id"))

    if not verification.get("questions"):
        questions = await generate_questions(llm, item)
        verification["questions"] = questions
        return {
            "verification": verification,
            "status": "verifying",
            "reply": "为确认所有权，请回答：" + " / ".join(questions),
        }

    result = await judge_answers(llm, item, verification.get("answers") or [])
    verification["result"] = result
    return {
        "verification": verification,
        "status": "disputed" if result["risk_level"] == "high" else "passed",
        "reply": result["judgement"],
    }


# ─────────────────────────── Chat（带检索）───────────────────────────


_CHAT_SYSTEM = """你是校园失物招领助手的对话入口。回答要简洁、友好、中文。
你会收到「用户的登记与匹配记录」作为上下文；请据此直接回答用户的查询，不要编造上下文中不存在的匹配。
若用户想登记失物/招领，引导其描述物品并上传照片；若要认领，引导其发起认领并接受核验。"""


async def retrieve_user_context(user_id: str | None, limit: int = 10) -> tuple[str, list[dict]]:
    """查询用户名下物品及其匹配，构造对话上下文与匹配列表。"""
    if not user_id:
        return "", []
    uid = uuid.UUID(user_id)
    lines: list[str] = []
    matches_out: list[dict] = []
    seen_matches: set[str] = set()

    async with SessionLocal() as session:
        items = (
            (
                await session.execute(
                    select(Item)
                    .where(Item.reporter_id == uid, Item.status != ItemStatus.removed)
                    .order_by(Item.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        for it in items:
            kind = "丢失" if it.type == ItemType.lost else "拾获"
            lines.append(f"- [{kind}] {it.title}（地点: {it.location_tag or '未知'}）")
            found = (
                (
                    await session.execute(
                        select(Match)
                        .where((Match.lost_item_id == it.id) | (Match.found_item_id == it.id))
                        .order_by(Match.score.desc())
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            for m in found:
                if str(m.id) in seen_matches:
                    continue
                seen_matches.add(str(m.id))
                other_id = m.found_item_id if m.lost_item_id == it.id else m.lost_item_id
                other = await session.get(Item, other_id)
                other_title = other.title if other else "未知物品"
                lines.append(f"    匹配 {m.score:.2f}：「{other_title}」— {m.reason or '无说明'}")
                matches_out.append(
                    {
                        "id": str(m.id),
                        "lost_item_id": str(m.lost_item_id),
                        "found_item_id": str(m.found_item_id),
                        "score": m.score,
                        "reason": m.reason,
                    }
                )
    return "\n".join(lines), matches_out


_HISTORY_LIMIT = 10


def build_chat_messages(context: str, history: list[dict[str, str]]) -> list[dict]:
    """拼装对话消息：system（含检索上下文）+ 最近若干轮历史。"""
    system = _CHAT_SYSTEM
    if context:
        system += f"\n\n【用户的登记与匹配记录】\n{context}"
    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(history[-_HISTORY_LIMIT:])
    return messages


async def chat_node(state: AgentState) -> AgentState:
    llm = get_llm()
    context, matches = await retrieve_user_context(state.get("user_id"))
    # route_only：仅做路由/检索，不生成回复（供流式接口复用同一张图）
    if state.get("route_only"):
        return {"matches": matches, "status": "routed"}
    messages = build_chat_messages(context, state.get("history") or [])
    reply = await llm.complete(messages, thinking=False)
    return {"reply": reply, "status": "answered", "matches": matches}


# ─────────────────────────── HITL（认领前人工确认）───────────────────────────


async def human_review_node(state: AgentState) -> AgentState:
    """认领前的人工确认。

    有 checkpointer 时用 `interrupt()` 暂停，等待外部用 `Command(resume=...)` 恢复；
    无持久化时无法暂停，直接放行。
    """
    decision = state.get("decision")
    if decision is not None:
        return {"decision": decision}
    if get_checkpointer() is None:
        return {"decision": "yes"}

    resumed = interrupt(
        {"action": "claim", "question": "确认要发起认领吗？回复 yes 继续，no 取消。"}
    )
    return {"decision": str(resumed)}


async def claim_node(state: AgentState) -> AgentState:
    """按人工确认结果处理认领请求。"""
    decision = (state.get("decision") or "").strip().lower()
    if decision not in {"yes", "y", "true", "确认", "是"}:
        return {"reply": "已取消认领。", "status": "cancelled"}
    return {
        "reply": "已受理你的认领请求。请到「认领」页选择对应匹配，完成核验问答后即可交换联系方式。",
        "status": "claiming",
    }


async def finish_node(state: AgentState) -> AgentState:
    """收尾：把助手回复写入历史。"""
    history = list(state.get("history") or [])
    reply = state.get("reply")
    if reply:
        history.append({"role": "assistant", "content": reply})
    return {"status": state.get("status", "done"), "history": history}


def match_status_of(score: float) -> MatchStatus:
    return MatchStatus.confirmed if score >= settings.match_high_threshold else MatchStatus.pending
