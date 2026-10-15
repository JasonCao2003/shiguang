const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type Match = {
  id: string;
  lost_item_id: string;
  found_item_id: string;
  score: number;
  reason: string | null;
};

export type ChatResponse = {
  thread_id: string;
  reply: string;
  intent: string | null;
  item_id: string | null;
  matches: Match[];
};

export async function chat(message: string, threadId?: string): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!res.ok) throw new Error(`chat 失败: ${res.status}`);
  return res.json();
}

export type ItemCreate = {
  type: "LOST" | "FOUND";
  title: string;
  description?: string;
  location_tag?: string;
};

export async function createItem(payload: ItemCreate) {
  const res = await fetch(`${BASE}/api/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`登记失败: ${res.status}`);
  return res.json();
}

export async function listItems() {
  const res = await fetch(`${BASE}/api/items`, { cache: "no-store" });
  if (!res.ok) throw new Error(`获取列表失败: ${res.status}`);
  return res.json();
}
