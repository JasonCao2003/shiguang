"use client";

import { useEffect, useRef, useState } from "react";

import {
  chatStream,
  clearToken,
  createItem,
  getMatches,
  getToken,
  type Item,
  listItems,
  login,
  type Match,
  register,
} from "@/lib/api";

export default function Home() {
  const [token, setTok] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setTok(getToken());
    setReady(true);
  }, []);

  function logout() {
    clearToken();
    setTok(null);
  }

  if (!ready) return null;
  if (!token) return <Auth onDone={() => setTok(getToken())} />;

  return (
    <main className="container">
      <header className="topbar">
        <div>
          <h1>Find · 校园失物招领</h1>
          <p className="muted">AI 智能匹配 · 对话助手</p>
        </div>
        <button className="ghost" onClick={logout}>
          退出
        </button>
      </header>

      <Tabs />
    </main>
  );
}

// ────────────────────────── 登录 / 注册 ──────────────────────────

function Auth({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, name || email);
        await login(email, password);
      }
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container">
      <div className="card auth">
        <h2>{mode === "login" ? "登录" : "注册"}</h2>
        {mode === "register" && (
          <>
            <label>昵称</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="如：小王" />
          </>
        )}
        <label>校园邮箱</label>
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@campus.edu"
          autoComplete="username"
        />
        <label>密码</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="至少 6 位"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
        />
        <button onClick={submit} disabled={busy || !email || password.length < 6}>
          {busy ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}
        </button>
        <p className="switch muted" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "没有账号？去注册 →" : "已有账号？去登录 →"}
        </p>
        {err && <p className="error">{err}</p>}
      </div>
    </main>
  );
}

// ────────────────────────── 标签页 ──────────────────────────

function Tabs() {
  const [tab, setTab] = useState<"browse" | "report" | "chat">("browse");
  const labels = { browse: "浏览", report: "登记", chat: "对话" } as const;

  return (
    <>
      <nav className="tabs">
        {(["browse", "report", "chat"] as const).map((t) => (
          <button
            key={t}
            className={tab === t ? "tab active" : "tab"}
            onClick={() => setTab(t)}
          >
            {labels[t]}
          </button>
        ))}
      </nav>

      {tab === "browse" && <Browse />}
      {tab === "report" && <Report />}
      {tab === "chat" && <Chat />}
    </>
  );
}

// ────────────────────────── 浏览 ──────────────────────────

function Browse() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    listItems()
      .then(setItems)
      .catch((e) => setErr((e as Error).message));
  }, []);

  if (err) return <div className="card error">{err}</div>;
  if (!items) return <div className="card muted">加载中…</div>;
  if (!items.length) return <div className="card muted">还没有物品，去「登记」发布一条吧。</div>;

  return (
    <div className="card">
      <strong>物品一览（{items.length}）</strong>
      <ul className="items">
        {items.map((i) => (
          <li key={i.id}>
            <span className={i.type === "LOST" ? "badge lost" : "badge found"}>
              {i.type === "LOST" ? "丢失" : "拾获"}
            </span>
            <b>{i.title}</b>
            {i.location_tag && <span className="muted"> · {i.location_tag}</span>}
            {i.color && <span className="muted"> · {i.color}</span>}
          </li>
        ))}
      </ul>
      <p className="muted">
        说明：公开列表不含物品的描述与显著特征，这些信息仅用于核验比对。
      </p>
    </div>
  );
}

// ────────────────────────── 登记 ──────────────────────────

function Report() {
  const [type, setType] = useState<"LOST" | "FOUND">("LOST");
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [place, setPlace] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState<{ item: Item; matches: Match[] } | null>(null);

  async function submit() {
    if (!title.trim() || busy) return;
    setBusy(true);
    setErr("");
    try {
      const item = await createItem({ type, title, description: desc, location_tag: place });
      const matches = await getMatches(item.id);
      setResult({ item, matches });
      setTitle("");
      setDesc("");
      setPlace("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="card">
        <strong>登记失物 / 招领</strong>
        <label>类型</label>
        <select value={type} onChange={(e) => setType(e.target.value as "LOST" | "FOUND")}>
          <option value="LOST">我丢了东西</option>
          <option value="FOUND">我捡到东西</option>
        </select>
        <label>物品名称</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="如：黑色钱包" />
        <label>详细描述（用于智能匹配与核验）</label>
        <textarea
          rows={3}
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="如：黑色牛皮钱包，里面有校园卡和一张照片，在图书馆三楼丢的"
        />
        <label>地点</label>
        <input value={place} onChange={(e) => setPlace(e.target.value)} placeholder="如：图书馆三楼" />
        <button onClick={submit} disabled={busy || !title.trim()}>
          {busy ? "匹配中…" : "提交并智能匹配"}
        </button>
        {err && <p className="error">{err}</p>}
      </div>

      {result && (
        <div className="card">
          <strong>已登记「{result.item.title}」</strong>
          {result.matches.length === 0 ? (
            <p className="muted">暂未找到匹配，已进入待匹配池，有新招领时会通知你。</p>
          ) : (
            <>
              <p className="muted">找到 {result.matches.length} 个候选匹配：</p>
              <ul className="items">
                {result.matches.map((m) => (
                  <li key={m.id}>
                    <span className="score">{m.score.toFixed(2)}</span>
                    <span>{m.reason}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </>
  );
}

// ────────────────────────── 对话 ──────────────────────────

type Msg = { role: "user" | "assistant"; text: string };

function Chat() {
  const [threadId, setThreadId] = useState<string | undefined>();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [matches, setMatches] = useState<Match[]>([]);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    boxRef.current?.scrollTo({ top: boxRef.current.scrollHeight });
  }, [messages, busy]);

  function patchLast(patch: (text: string) => string) {
    setMessages((m) => {
      const copy = [...m];
      const last = copy[copy.length - 1];
      copy[copy.length - 1] = { ...last, text: patch(last.text) };
      return copy;
    });
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text }, { role: "assistant", text: "" }]);
    try {
      await chatStream(
        text,
        {
          onMeta: (meta) => {
            setThreadId(meta.thread_id);
            if (meta.matches?.length) setMatches(meta.matches);
          },
          onDelta: (d) => patchLast((t) => t + d),
          onError: (msg) => patchLast((t) => `${t}\n（出错了：${msg}）`),
        },
        threadId,
      );
    } catch (e) {
      patchLast((t) => `${t}\n（出错了：${(e as Error).message}）`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {matches.length > 0 && (
        <div className="card">
          <strong>为你找到的匹配</strong>
          <ul className="items">
            {matches.map((m) => (
              <li key={m.id}>
                <span className="score">{m.score.toFixed(2)}</span>
                <span>{m.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card chat">
        <div className="chatbox" ref={boxRef}>
          {messages.length === 0 && (
            <p className="muted">试试问：“我丢的黑色钱包有消息吗？”</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "bubble user" : "bubble assistant"}>
              {m.text || (busy && i === messages.length - 1 ? "▍" : "")}
            </div>
          ))}
        </div>
        <label>说点什么</label>
        <textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="回车发送，Shift+回车换行"
        />
        <button onClick={send} disabled={busy || !input.trim()}>
          {busy ? "回复中…" : "发送"}
        </button>
      </div>
    </>
  );
}
