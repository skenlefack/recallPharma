"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { ArrowRightIcon, FlagIcon, SendIcon, SparkIcon, ThumbUpIcon, TrashIcon } from "@/components/icons";
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
  // Extraits de RCP : affichés tels quels, dans leur langue, avec leur source (CT-COP-02).
  passages?: { id: string; ma_id: string; text: string; rubric: string; language: string; product: string; source: string }[];
  comparisons?: { id: string; name: string; present: string[]; absent: string[]; differences: string[] }[];
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

const SUGGESTIONS = [
  "Quels produits à base d'ivermectine sont autorisés pour les bovins ?",
  "Quels médicaments à base d'oxytétracycline sont autorisés ?",
  "Quelles AMM sont suspendues en ce moment ?",
];

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
    <div className="chat">
      <header className="chat-head">
        <span className="chat-avatar" aria-hidden>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/symbole.png" alt="" width={34} height={34} />
        </span>
        <div className="chat-title">
          <strong>Copilot RecallPharma</strong>
          <span className="chat-status">
            <span className="chat-dot" aria-hidden /> Modèle open source · registre de {name}
          </span>
        </div>
        <label className="chat-jurisdiction">
          <span className="sr-only">Juridiction</span>
          <select value={jurisdiction} onChange={(e) => changeJurisdiction(e.target.value)} disabled={busy}>
            {jurisdictions.map((j) => (
              <option key={j.code} value={j.code}>
                {j.name}
              </option>
            ))}
          </select>
        </label>
        {turns.length > 0 && (
          <button type="button" className="chat-erase" onClick={erase} disabled={busy} title="Effacer la conversation">
            <TrashIcon size={16} /> <span>Effacer</span>
          </button>
        )}
      </header>

      <div className="chat-thread">
        {turns.length === 0 && (
          <div className="chat-empty">
            <span className="chat-empty-icon" aria-hidden>
              <SparkIcon size={30} />
            </span>
            <h2>Posez votre question au registre</h2>
            <p>Statut des AMM, délais d&apos;attente, textes des RCP, comparaisons entre juridictions.</p>
            <div className="chat-suggestions">
              {SUGGESTIONS.map((q) => (
                <button key={q} type="button" onClick={() => setQuestion(q)} disabled={busy}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <section key={i} className="copilot-turn" aria-live="polite">
            <p className="copilot-question">
              <span className="sr-only">Question :</span>
              {t.question}
            </p>
            <div className="chat-reply">
              <span className="chat-avatar small" aria-hidden>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/brand/symbole.png" alt="" width={26} height={26} />
              </span>
              <div className="chat-reply-body">
                {t.step && (
                  <p className="chat-step">
                    <span className="chat-typing" aria-hidden>
                      <i />
                      <i />
                      <i />
                    </span>
                    {STEP_LABEL[t.step] ?? t.step}
                  </p>
                )}
                {t.records && <RecordsView records={t.records} />}
                {t.answer && (
                  <div className={`chat-answer kind-${t.answer.kind}`}>
                    <p className="chat-answer-text">{t.answer.text}</p>
                    <p className="chat-answer-context">{t.answer.context.line}</p>
                    {t.answer.context.sources.length > 0 && (
                      <p className="chat-answer-sources">
                        <strong>Sources</strong> {t.answer.context.sources.join(" ; ")}
                      </p>
                    )}
                    <p className="chat-answer-mention">{t.answer.mention}</p>
                    <div className="chat-actions">
                      {t.answer.actions
                        .filter((a) => a.href)
                        .map((a) => (
                          <Link key={a.href} href={a.href!} className="chat-action">
                            {a.label}
                            {a.href!.startsWith("/amm/") ? ` ${a.href!.slice(5)}` : ""} <ArrowRightIcon size={13} />
                          </Link>
                        ))}
                      {t.messageId && !t.feedback && (
                        <span className="chat-feedback">
                          <button type="button" onClick={() => sendFeedback(i, "utile")}>
                            <ThumbUpIcon size={14} /> Utile
                          </button>
                          <button type="button" onClick={() => sendFeedback(i, "erreur signalée")}>
                            <FlagIcon size={14} /> Signaler une erreur
                          </button>
                        </span>
                      )}
                      {t.feedback && <span className="chat-feedback-done">{t.feedback}</span>}
                    </div>
                  </div>
                )}
                {t.error && (
                  <div className="banner tone-gris" role="status">
                    <div>{t.error}</div>
                  </div>
                )}
              </div>
            </div>
          </section>
        ))}
        <div ref={bottom} />
      </div>

      <form onSubmit={submit} className="chat-composer">
        <label className="chat-input">
          <span className="sr-only">Votre question (registre de {name})</span>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            maxLength={2000}
            rows={2}
            placeholder="Ex. : Quels produits à base d'ivermectine sont autorisés pour les bovins ?"
            disabled={busy}
          />
        </label>
        <button type="submit" className="chat-send" disabled={busy || !question.trim()}>
          {busy ? (
            "En cours…"
          ) : (
            <>
              Envoyer <SendIcon size={16} />
            </>
          )}
        </button>
        <p className="chat-hint">
          Entrée pour envoyer, Maj + Entrée pour aller à la ligne{problem && <> · {problem}</>}
        </p>
      </form>
    </div>
  );
}

function RecordsView({ records }: { records: RecordsEvent }) {
  const compared = (records.comparisons ?? []).length > 0;
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
                {compared && <th>Juridiction</th>}
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
                  {compared && <td className="small">{r.jurisdiction}</td>}
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
      {(records.comparisons ?? []).map((c) => (
        <p key={c.id} className="small">
          {c.name} : présent dans {c.present.join(", ") || "aucune juridiction"}
          {c.absent.length > 0 && <> ; absent de {c.absent.join(", ")}</>} ; écarts :{" "}
          {c.differences.join(", ") || "aucun"}. Chaque AMM est lue avec son propre RCP.
        </p>
      ))}
      {(records.passages ?? []).map((p) => (
        <figure key={p.id} className="card" style={{ margin: 0 }}>
          <blockquote lang={p.language} style={{ margin: 0 }}>
            {p.text}
          </blockquote>
          <figcaption className="small muted">
            <Link href={`/amm/${p.ma_id}`}>{p.product}</Link> · rubrique {p.rubric} · {p.source}
            {p.language !== "fr" && <> · texte en {p.language === "en" ? "anglais" : p.language}</>}
          </figcaption>
        </figure>
      ))}
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
