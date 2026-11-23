import Link from "next/link";
import { redirect } from "next/navigation";

import { ProposalEditor } from "@/components/ProposalEditor";
import { type Jurisdiction, type Substance, api, currentUser } from "@/lib/api";
import { type DocumentOut, emptyPayload } from "@/lib/proposal";

const CRITICAL_FIELDS = {
  denomination: "Dénomination",
  ma_number: "Numéro d'AMM",
  jurisdiction: "Juridiction",
  events: "Événements et dates",
  holder: "Titulaire",
  components: "Substances et teneurs",
  pharmaceutical_form: "Forme pharmaceutique",
  routes: "Voies d'administration",
  target_species: "Espèces cibles",
  posology: "Posologie",
  withdrawal_periods: "Délais d'attente",
  prohibitions: "Interdictions",
  contraindications: "Contre-indications",
  dispensing_condition: "Conditions de délivrance",
};

export default async function NewProposalPage() {
  if (!(await currentUser())) redirect("/connexion?next=/validation/nouvelle");
  const [documents, substances, jurisdictions] = await Promise.all([
    api<DocumentOut[]>("/v1/curation/documents"),
    api<Substance[]>("/v1/substances"),
    api<Jurisdiction[]>("/v1/jurisdictions"),
  ]);
  return (
    <>
      <p className="small">
        <Link href="/validation">← Validation</Link>
      </p>
      <h1>Nouvelle proposition</h1>
      <p className="muted">La fiche reste invisible du public jusqu&apos;à sa publication après les deux validations.</p>
      <ProposalEditor
        initial={emptyPayload()}
        initialProvenance={{}}
        criticalFields={CRITICAL_FIELDS}
        documents={documents}
        substances={substances}
        jurisdictions={jurisdictions}
      />
    </>
  );
}
