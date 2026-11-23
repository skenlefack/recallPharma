"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff, describe } from "@/lib/bff";
import type { DocumentOut } from "@/lib/proposal";

export function DocumentUpload({ documents }: { documents: DocumentOut[] }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<DocumentOut | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    if (!data.get("replaces_document_id")) data.delete("replaces_document_id");
    setBusy(true);
    setError(null);
    try {
      setDone(await bff<DocumentOut>("/v1/curation/documents", { method: "POST", body: data }));
      form.reset();
      router.refresh();
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card stack" onSubmit={submit}>
      <div className="grid2">
        <label className="field">
          Fichier (PDF, image)
          <input type="file" name="file" required accept="application/pdf,image/*" />
        </label>
        <label className="field">
          Titre
          <input name="title" required placeholder="Décision d'AMM n° …" />
        </label>
        <label className="field">
          Nature
          <select name="nature" defaultValue="officielle">
            <option value="officielle">officielle (autorité)</option>
            <option value="déclarative">déclarative (titulaire, distributeur)</option>
          </select>
        </label>
        <label className="field">
          Date du document
          <input type="date" name="document_date" required />
        </label>
        <label className="field">
          Remplace le document
          <select name="replaces_document_id" defaultValue="">
            <option value="">— nouveau document —</option>
            {documents.map((d) => (
              <option key={d.id} value={d.id}>
                n° {d.id} — {d.title}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Dernière édition disponible
          <select name="latest_edition" defaultValue="true">
            <option value="true">oui</option>
            <option value="false">non</option>
          </select>
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      {done && (
        <p className="small">
          Document n° {done.id} enregistré, empreinte <span className="mono">{done.sha256}</span>.
        </p>
      )}
      <div>
        <button type="submit" disabled={busy}>
          Déposer
        </button>
      </div>
    </form>
  );
}
