import Link from "next/link";
import { redirect } from "next/navigation";

import { DocumentUpload } from "@/components/DocumentUpload";
import { api, currentUser } from "@/lib/api";
import type { DocumentOut } from "@/lib/proposal";

export default async function DocumentsPage() {
  if (!(await currentUser())) redirect("/connexion?next=/validation/documents");
  const documents = await api<DocumentOut[]>("/v1/curation/documents");
  return (
    <>
      <p className="small">
        <Link href="/validation">← Validation</Link>
      </p>
      <h1>Documents sources</h1>
      <p className="muted">
        Chaque document est conservé tel quel, avec son empreinte SHA-256. Un même fichier n&apos;est accepté qu&apos;une fois ;
        une version corrigée se rattache à la précédente.
      </p>
      <DocumentUpload documents={documents} />
      <h2>Déposés</h2>
      <div className="table-scroll card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>N°</th>
              <th>Titre</th>
              <th>Nature</th>
              <th>Date</th>
              <th>Empreinte</th>
              <th>Remplace</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((d) => (
              <tr key={d.id}>
                <td>{d.id}</td>
                <td>
                  {d.title}
                  <div className="muted small">{d.filename}</div>
                </td>
                <td>{d.nature}</td>
                <td>{d.document_date}</td>
                <td className="mono small">{d.sha256 ? `${d.sha256.slice(0, 12)}…` : "—"}</td>
                <td>{d.replaces_document_id ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
