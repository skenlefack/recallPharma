"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { Banners, StatusBadge } from "@/components/regulatory";
import type { Schemas } from "@/lib/api";
import { bff, describe } from "@/lib/bff";

type Row = Schemas["CopilotRow"];
type Banner = Schemas["BannerOut"];
type Jurisdiction = Schemas["JurisdictionOut"];

type RecordsEvent = {
  banners: Banner[];
  rows: Row[];
  total: number | null;
  apart: { id: string; label: string }[];
  elsewhere: Row[];
  notices: string[];
  jurisdiction: string;
};
type AnswerEvent = {
  kind: "answer" | "fallback" | "abstention";
  text: string;
  reason?: string;
  context: { line: string; sources: string[] };
  mention: string;
  actions: { label: string; href?: string; action?: string }[];
};
type Turn = {
  question: string;
  step?: string;
  records?: RecordsEvent;
  answer?: AnswerEvent;
  error?: string;
  messageId?: string;
  feedback?: string;
};

const STEP_LABEL: Record<string, string> = {
  réception: "Lecture de la question…",
  planification: "Interrogation du registre…",
  rédaction: "Rédaction et contrôle de la réponse…",
};

/** Lecture progressive d'un flux text/event-stream renvoyé par le BFF. */
async function* events(res: Response): AsyncGenerator<[string, Record<string, unknown>]> {
  const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let name = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) yield [name, JSON.parse(data) as Record<string, unknown>];
    }
  }
}

export function CopilotChat({ jurisdictions, defaultJurisdiction }: { jurisdictions: Jurisdiction[]; defaultJurisdiction: string }) {
  const [jurisdiction, setJurisdiction] = useState(defaultJurisdiction);
  const [conversation, setConversation] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const update = (i: number, patch: Partial<Turn>) =>
    setTurns((ts) => ts.map((t, k) => (k === i ? { ...t, ...patch } : t)));

  async function ensureConversation(): Promise<string> {
    if (conversation) return conversation;
    const c = await bff<{ id: string }>("/v1/copilot/conversations", { method: "POST", body: JSON.stringify({ jurisdiction }) });
    setConversation(c.id);
    return c.id;
  }

  async function changeJurisdiction(code: string) {
    setJurisdiction(code);
    if (conversation) {
      await bff(`/v1/copilot/conversations/${conversation}`, { method: "PUT", body: JSON.stringify({ jurisdiction: code }) }).catch(
        (e) => setProblem(describe(e)),
      );
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setProblem(null);
    const index = turns.length;
    setTurns((ts) => [...ts, { question: text }]);
    setQuestion("");
    try {
      const id = await ensureConversation();
      const res = await fetch(`/api/bff/v1/copilot/conversations/${id}/messages`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content: text }),
      });
      if (!res.ok) {
        const p = await res.json().catch(() => ({}));
        update(index, { error: p.detail ?? p.title ?? `Erreur ${res.status}` });
        return;
      }
      for await (const [name, data] of events(res)) {
        if (name === "status") update(index, { step: String(data.step) });
        else if (name === "records") update(index, { records: data as unknown as RecordsEvent });
        else if (name === "answer") update(index, { answer: data as unknown as AnswerEvent, step: undefined });
        else if (name === "error") update(index, { error: String(data.message), step: undefined });
        else if (name === "done") update(index, { messageId: String(data.message_id) });
        bottom.current?.scrollIntoView({ block: "end" });
      }
    } catch (err) {
      update(index, { error: describe(err), step: undefined });
    } finally {
      setBusy(false);
    }
  }

  async function sendFeedback(i: number, rating: "utile" | "erreur signalée") {
    const t = turns[i];
    if (!t.messageId) return;
    try {
      const r = await bff<{ status: string; ticket?: string }>(`/v1/copilot/messages/${t.messageId}/feedback`, {
        method: "POST",
        body: JSON.stringify({ rating }),
      });
      update(i, { feedback: r.ticket ? `Signalement reçu (ticket ${r.ticket}).` : "Merci, retour enregistré." });
    } catch (e) {
      update(i, { feedback: describe(e) });
    }
  }

  async function erase() {
    if (conversation) await bff(`/v1/copilot/conversations/${conversation}`, { method: "DELETE" }).catch(() => undefined);
    setConversation(null);
    setTurns([]);
  }

  const name = jurisdictions.find((j) => j.code === jurisdiction)?.name ?? jurisdiction;

  return (
    <div className="stack">
      <div className="row" style={{ alignItems: "end" }}>
        <label className="field">
          Juridiction
          <select value={jurisdiction} onChange={(e) => changeJurisdiction(e.target.value)} disabled={busy}>
            {jurisdictions.map((j) => (
              <option key={j.code} value={j.code}>
                {j.name}
              </option>
            ))}
          </select>
        </label>
        {turns.length > 0 && (
          <button type="button" className="secondary" onClick={erase} disabled={busy}>
            Effacer la conversation
          </button>
        )}
      </div>

      {turns.map((t, i) => (
        <section key={i} className="stack copilot-turn" aria-live="polite">
          <p className="copilot-question">
            <strong>Question :</strong> {t.question}
          </p>
          {t.step && <p className="muted small">{STEP_LABEL[t.step] ?? t.step}</p>}
          {t.records && <RecordsView records={t.records} />}
          {t.answer && (
            <div className="card stack">
              <p style={{ margin: 0 }} className={t.answer.kind === "answer" ? "" : "muted"}>
                {t.answer.text}
              </p>
              <p className="small muted" style={{ margin: 0 }}>
                {t.answer.context.line}
              </p>
              {t.answer.context.sources.length > 0 && (
                <p className="small" style={{ margin: 0 }}>
                  Sources : {t.answer.context.sources.join(" ; ")}
                </p>
              )}
              <p className="small" style={{ margin: 0 }}>
                <em>{t.answer.mention}</em>
              </p>
              <div className="row small">
                {t.answer.actions
                  .filter((a) => a.href)
                  .map((a) => (
                    <Link key={a.href} href={a.href!}>
                      {a.label}
                      {a.href!.startsWith("/amm/") ? ` ${a.href!.slice(5)}` : ""}
                    </Link>
                  ))}
                {t.messageId && !t.feedback && (
                  <>
                    <button type="button" className="link" onClick={() => sendFeedback(i, "utile")}>
                      Utile
                    </button>
                    <button type="button" className="link" onClick={() => sendFeedback(i, "erreur signalée")}>
                      Signaler une erreur
                    </button>
                  </>
                )}
                {t.feedback && <span className="muted">{t.feedback}</span>}
              </div>
            </div>
          )}
          {t.error && (
            <div className="banner tone-gris" role="status">
              <div>{t.error}</div>
            </div>
          )}
        </section>
      ))}
      <div ref={bottom} />

      <form onSubmit={submit} className="card stack">
        <label className="field">
          Votre question (registre de {name})
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="Ex. : Quels produits à base d'ivermectine sont autorisés pour les bovins ?"
            disabled={busy}
          />
        </label>
        <div className="row">
          <button type="submit" disabled={busy || !question.trim()}>
            {busy ? "En cours…" : "Envoyer"}
          </button>
          {problem && <span className="small">{problem}</span>}
        </div>
      </form>
    </div>
  );
}

function RecordsView({ records }: { records: RecordsEvent }) {
  return (
    <div className="stack">
      <Banners banners={records.banners} />
      {records.notices.map((n) => (
        <div key={n} className="banner tone-gris" role="note">
          <div>{n}</div>
        </div>
      ))}
      {records.rows.length > 0 && (
        <div className="table-scroll card" style={{ padding: 0 }}>
          <table>
            <caption className="small muted" style={{ textAlign: "left", padding: "8px 12px" }}>
              {records.total} enregistrement{(records.total ?? 0) > 1 ? "s" : ""} du registre (total calculé par le registre)
            </caption>
            <thead>
              <tr>
                <th>Produit</th>
                <th>Désignation</th>
                <th>N° d&apos;AMM</th>
                <th>Statut</th>
                <th>Preuve</th>
                <th>Vérifiée le</th>
              </tr>
            </thead>
            <tbody>
              {records.rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/amm/${r.id}`}>{r.name}</Link>
                  </td>
                  <td className="small">{r.designation}</td>
                  <td className="mono small">{r.ma_number}</td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="small">{r.evidence_level}</td>
                  <td className="small">{r.verified_at ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {records.apart.length > 0 && (
        <p className="small">
          Listés à part (délai non comparable) :{" "}
          {records.apart.map((a, i) => (
            <span key={a.id}>
              {i > 0 && " ; "}
              <Link href={`/amm/${a.id}`}>{a.id}</Link> ({a.label})
            </span>
          ))}
        </p>
      )}
      {records.elsewhere.length > 0 && (
        <p className="small">
          Autorisé ailleurs, à titre d&apos;information :{" "}
          {records.elsewhere.map((r, i) => (
            <span key={r.id}>
              {i > 0 && " ; "}
              <Link href={`/amm/${r.id}`}>{r.name}</Link> ({r.jurisdiction})
            </span>
          ))}
        </p>
      )}
    </div>
  );
}
