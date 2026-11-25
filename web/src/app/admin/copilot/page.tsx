import { ChatIcon, FlagIcon, ThumbUpIcon } from "@/components/icons";
import { type Feedback, type Overview, formatDateTime } from "@/lib/admin";
import { api } from "@/lib/api";

export default async function AdminCopilot() {
  const [feedback, o] = await Promise.all([
    api<Feedback[]>("/v1/admin/copilot/feedback"),
    api<Overview>("/v1/admin/overview"),
  ]);
  const kpis = [
    { icon: ChatIcon, label: "Conversations", value: o.copilot.conversations ?? 0 },
    { icon: ChatIcon, label: "Questions (30 jours)", value: o.copilot.questions_30j ?? 0 },
    { icon: ThumbUpIcon, label: "Réponses jugées utiles", value: o.copilot.utile ?? 0, tone: "ok" },
    { icon: FlagIcon, label: "Erreurs signalées", value: o.copilot.erreurs ?? 0, tone: "danger" },
  ];
  return (
    <>
      <header className="admin-head">
        <div>
          <span className="section-kicker">Assistant IA</span>
          <h1>Copilot</h1>
          <p className="muted">Retours des utilisateurs sur les réponses, avec la question posée et le modèle utilisé.</p>
        </div>
      </header>
      <section className="admin-kpis four">
        {kpis.map(({ icon: Icon, label, value, tone }) => (
          <div key={label} className={`admin-kpi${tone ? ` tone-${tone}` : ""}`}>
            <span className="admin-kpi-icon">
              <Icon size={22} />
            </span>
            <span className="admin-kpi-value">{value}</span>
            <span className="admin-kpi-label">{label}</span>
          </div>
        ))}
      </section>
      <section className="admin-stack">
        {feedback.length === 0 && (
          <div className="admin-card">
            <p className="muted admin-empty">Aucun retour pour l&apos;instant.</p>
          </div>
        )}
        {feedback.map((f) => (
          <article key={f.message_id} className={`admin-card admin-feedback ${f.rating === "utile" ? "ok" : "danger"}`}>
            <header>
              <span className={`admin-state ${f.rating === "utile" ? "on" : "danger"}`}>
                {f.rating === "utile" ? <ThumbUpIcon size={13} /> : <FlagIcon size={13} />} {f.rating}
              </span>
              <span className="small muted">
                {formatDateTime(f.given_at)} · compte <span className="mono">{f.account_id}</span>
                {f.model_id && <> · modèle {f.model_id}</>}
              </span>
            </header>
            {f.question && (
              <p className="admin-feedback-q">
                <strong>Question</strong> {f.question}
              </p>
            )}
            <p className="admin-feedback-a">
              <strong>Réponse</strong> {f.answer}
            </p>
            {f.comment && <p className="small">Commentaire : {f.comment}</p>}
          </article>
        ))}
      </section>
    </>
  );
}
