const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// ─────────────── 令牌 ───────────────

const TOKEN_KEY = "find_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function ensureOk(res: Response, action: string): Promise<void> {
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(`${action}失败：${detail}`);
  }
}

// ─────────────── 类型 ───────────────

export type Match = {
  id: string;
  lost_item_id: string;
  found_item_id: string;
  score: number;
  reason: string | null;
};

export type Item = {
  id: string;
  type: "LOST" | "FOUND";
  title: string;
  category?: string | null;
  color?: string | null;
  location_tag?: string | null;
  status: string;
  created_at: string;
  // 仅登记人可见
  description?: string | null;
  distinguishing_features?: string | null;
};

// ─────────────── 认证 ───────────────

export async function register(email: string, password: string, name: string): Promise<void> {
  const res = await fetch(`${BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name }),
  });
  await ensureOk(res, "注册");
}

export async function login(email: string, password: string): Promise<string> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  await ensureOk(res, "登录");
  const data = await res.json();
  setToken(data.access_token);
  return data.access_token as string;
}

// ─────────────── 物品 ───────────────

export async function listItems(): Promise<Item[]> {
  const res = await fetch(`${BASE}/api/items`, { cache: "no-store" });
  await ensureOk(res, "获取列表");
  return res.json();
}

export type ItemCreate = {
  type: "LOST" | "FOUND";
  title: string;
  description?: string;
  location_tag?: string;
};

export async function createItem(payload: ItemCreate): Promise<Item> {
  const res = await fetch(`${BASE}/api/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  await ensureOk(res, "登记");
  return res.json();
}

export async function getMatches(itemId: string): Promise<Match[]> {
  const res = await fetch(`${BASE}/api/items/${itemId}/matches`, {
    headers: authHeaders(),
  });
  await ensureOk(res, "获取匹配");
  return res.json();
}

// ─────────────── 认领 / 核验 ───────────────

export type Claim = {
  id: string;
  match_id: string;
  claimant_id: string;
  status: "initiated" | "verifying" | "passed" | "rejected" | "disputed" | "contacted";
  risk_level: "low" | "medium" | "high";
  confidence: number | null;
};

export type VerificationResult = {
  passed: boolean;
  confidence: number;
  risk_level: "low" | "medium" | "high";
  judgement: string;
};

export type ContactExchange = {
  id: string;
  claim_id: string;
  lost_contact: string | null;
  found_contact: string | null;
  consent_lost: boolean;
  consent_found: boolean;
};

export async function listClaims(): Promise<Claim[]> {
  const res = await fetch(`${BASE}/api/claims`, { headers: authHeaders() });
  await ensureOk(res, "获取认领列表");
  return res.json();
}

export async function createClaim(matchId: string): Promise<Claim> {
  const res = await fetch(`${BASE}/api/claims`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ match_id: matchId }),
  });
  await ensureOk(res, "发起认领");
  return res.json();
}

export async function getQuestions(claimId: string): Promise<string[]> {
  const res = await fetch(`${BASE}/api/claims/${claimId}/questions`, {
    headers: authHeaders(),
  });
  await ensureOk(res, "获取核验问题");
  const items: { question: string }[] = await res.json();
  return items.map((q) => q.question);
}

export async function verifyClaim(
  claimId: string,
  answers: { question: string; answer: string }[],
): Promise<VerificationResult> {
  const res = await fetch(`${BASE}/api/claims/${claimId}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(answers),
  });
  await ensureOk(res, "提交核验");
  return res.json();
}

export async function exchangeContacts(claimId: string): Promise<ContactExchange> {
  const res = await fetch(`${BASE}/api/claims/${claimId}/exchange-contacts?consent=true`, {
    method: "POST",
    headers: authHeaders(),
  });
  await ensureOk(res, "交换联系方式");
  return res.json();
}

// ─────────────── 对话（SSE） ───────────────

export type ResumeResult = {
  thread_id: string;
  reply: string;
  interrupted: boolean;
  interrupt: { action?: string; question?: string } | null;
};

export async function resumeChat(threadId: string, decision: string): Promise<ResumeResult> {
  const res = await fetch(`${BASE}/api/chat/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ thread_id: threadId, decision }),
  });
  await ensureOk(res, "恢复会话");
  return res.json();
}
export type StreamHandlers = {
  onMeta?: (meta: { thread_id: string; matches: Match[] }) => void;
  onDelta?: (text: string) => void;
  onInterrupt?: (payload: { action?: string; question?: string }) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

export async function chatStream(
  message: string,
  handlers: StreamHandlers,
  threadId?: string,
): Promise<void> {
  const res = await fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`对话失败：${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = /^event: (.+)$/m.exec(block)?.[1]?.trim();
      const dataLine = /^data: (.+)$/m.exec(block)?.[1]?.trim();
      if (!event || !dataLine) continue;
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(dataLine);
      } catch {
        continue;
      }
      if (event === "meta") {
        handlers.onMeta?.(data as { thread_id: string; matches: Match[] });
      } else if (event === "delta") {
        handlers.onDelta?.(String(data.delta ?? ""));
      } else if (event === "interrupt") {
        handlers.onInterrupt?.(data as { action?: string; question?: string });
      } else if (event === "done") {
        handlers.onDone?.();
      } else if (event === "error") {
        handlers.onError?.(String(data.message ?? "未知错误"));
      }
    }
  }
}
