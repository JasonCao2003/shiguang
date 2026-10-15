"use client";

import { useState } from "react";
import { chat, createItem } from "@/lib/api";

type Msg = { role: "user" | "assistant"; text: string };

export default function Home() {
  const [threadId, setThreadId] = useState<string | undefined>();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  const [type, setType] = useState<"LOST" | "FOUND">("LOST");
  const [title, setTitle] = useState("");
  const [place, setPlace] = useState("");

  async function send() {
    if (!input.trim()) return;
    setMessages((m) => [...m, { role: "user", text: input }]);
    setBusy(true);
    try {
      const res = await chat(input, threadId);
      setThreadId(res.thread_id);
      setMessages((m) => [...m, { role: "assistant", text: res.reply }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `出错了：${(e as Error).message}` },
      ]);
    } finally {
      setInput("");
      setBusy(false);
    }
  }

  async function submitItem() {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await createItem({ type, title, location_tag: place });
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `已提交「${title}」，正在为你匹配…` },
      ]);
      setTitle("");
      setPlace("");
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `登记失败：${(e as Error).message}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container">
      <h1>Find · 校园失物招领</h1>
      <p className="muted">拍照描述即可，AI 帮你把失物与招领智能匹配。</p>

      <div className="card">
        <strong>登记失物 / 招领</strong>
        <label>类型</label>
        <select value={type} onChange={(e) => setType(e.target.value as "LOST" | "FOUND")}>
          <option value="LOST">我丢了东西</option>
          <option value="FOUND">我捡到东西</option>
        </select>
        <label>物品名称</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="如：黑色雨伞" />
        <label>地点</label>
        <input
          value={place}
          onChange={(e) => setPlace(e.target.value)}
          placeholder="如：图书馆三楼"
        />
        <button onClick={submitItem} disabled={busy}>
          提交
        </button>
      </div>

      <div className="card">
        <strong>对话助手</strong>
        <div>
          {messages.map((m, i) => (
            <div key={i} className="reply">
              <span className="muted">{m.role === "user" ? "我：" : "助手："}</span>
              {m.text}
            </div>
          ))}
        </div>
        <label>说点什么</label>
        <textarea
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="如：我上周在图书馆丢的蓝色水杯有消息吗？"
        />
        <button onClick={send} disabled={busy}>
          发送
        </button>
      </div>
    </main>
  );
}
