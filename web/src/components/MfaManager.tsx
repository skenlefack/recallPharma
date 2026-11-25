"use client";

import QRCode from "qrcode";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AlertTriangleIcon, ArrowRightIcon, CheckShieldIcon, KeyIcon, LockIcon } from "@/components/icons";
import { bff, describe } from "@/lib/bff";

type Setup = { secret: string; otpauth_uri: string };

type Props = { enabled: boolean; required?: boolean; next?: string };

/**
 * Activation de la double authentification : QR code à scanner, puis premier code pour confirmer. Obligatoire pour les
 * validateurs et les administrateurs (`required`) : elle ne peut alors pas être désactivée.
 */
export function MfaManager({ enabled: initial, required = false, next }: Props) {
  const router = useRouter();
  const [enabled, setEnabled] = useState(initial);
  const [setup, setSetup] = useState<(Setup & { qr: string }) | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (e) {
      setMessage({ tone: "error", text: describe(e) });
    } finally {
      setBusy(false);
    }
  }

  const start = () =>
    run(async () => {
      const s = await bff<Setup>("/v1/me/mfa/setup", { method: "POST" });
      const qr = await QRCode.toString(s.otpauth_uri, { type: "svg", margin: 1, width: 200, errorCorrectionLevel: "M" });
      setSetup({ ...s, qr });
      setCode("");
    });

  const confirm = (e: React.FormEvent) => {
    e.preventDefault();
    return run(async () => {
      await bff("/v1/me/mfa/activate", { method: "POST", body: JSON.stringify({ code: code.replace(/\s/g, "") }) });
      setEnabled(true);
      setSetup(null);
      setCode("");
      setMessage({ tone: "ok", text: "Double authentification activée : le code sera demandé à chaque connexion." });
      router.refresh(); // l'en-tête cesse de rediriger vers cette page
    });
  };

  const disable = (e: React.FormEvent) => {
    e.preventDefault();
    return run(async () => {
      await bff("/v1/me/mfa/disable", { method: "POST", body: JSON.stringify({ code: code.replace(/\s/g, "") }) });
      setEnabled(false);
      setCode("");
      setMessage({ tone: "ok", text: "Double authentification désactivée." });
    });
  };

  const codeField = (
    <div className="auth-input auth-code">
      <KeyIcon size={18} />
      <input
        value={code}
        onChange={(e) => setCode(e.target.value)}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={7}
        placeholder="123 456"
        aria-label="Code à 6 chiffres"
        required
      />
    </div>
  );

  return (
    <div className="mfa">
      {required && !enabled && (
        <div className="mfa-required" role="alert">
          <AlertTriangleIcon size={20} />
          <div>
            <strong>Activation obligatoire pour votre rôle</strong>
            <p>
              Les validateurs et les administrateurs protègent leur compte par un second facteur. L&apos;accès au
              back-office et à l&apos;administration s&apos;ouvre dès l&apos;activation.
            </p>
          </div>
        </div>
      )}
      {message && (
        <div className={`admin-flash ${message.tone}`} role="status">
          <span>{message.text}</span>
        </div>
      )}

      <div className={`mfa-status ${enabled ? "on" : "off"}`}>
        <span className="mfa-status-icon" aria-hidden>
          {enabled ? <CheckShieldIcon size={26} /> : <LockIcon size={26} />}
        </span>
        <div>
          <strong>{enabled ? "Double authentification active" : "Double authentification inactive"}</strong>
          <p className="muted">
            {enabled
              ? "Un code de votre application d'authentification est demandé après le mot de passe."
              : "Ajoutez un second facteur : même avec votre mot de passe, personne ne pourra se connecter sans votre téléphone."}
          </p>
        </div>
      </div>

      {!enabled && !setup && (
        <button type="button" className="auth-submit" onClick={start} disabled={busy}>
          Activer la double authentification
        </button>
      )}

      {setup && (
        <form className="mfa-setup" onSubmit={confirm}>
          <ol className="mfa-steps">
            <li>
              <strong>Installez une application d&apos;authentification</strong> sur votre téléphone : FreeOTP, Google
              Authenticator ou Microsoft Authenticator.
            </li>
            <li>
              <strong>Scannez ce QR code</strong> avec l&apos;application.
              <div className="mfa-qr" dangerouslySetInnerHTML={{ __html: setup.qr }} />
              <span className="small muted">
                Impossible de scanner ? Saisissez cette clé : <code className="admin-secret mfa-secret">{setup.secret}</code>
              </span>
            </li>
            <li>
              <strong>Saisissez le code affiché</strong> pour confirmer.
              {codeField}
            </li>
          </ol>
          <div className="admin-form-actions">
            <button type="button" className="admin-btn" onClick={() => setSetup(null)}>
              Annuler
            </button>
            <button type="submit" className="admin-btn primary" disabled={busy || code.replace(/\s/g, "").length !== 6}>
              Confirmer et activer
            </button>
          </div>
        </form>
      )}

      {enabled && next && (
        <Link href={next} className="auth-submit">
          Continuer <ArrowRightIcon size={16} />
        </Link>
      )}

      {enabled && required && (
        <p className="small muted">
          Obligatoire pour votre rôle : elle ne peut pas être désactivée. Téléphone perdu ? Votre administrateur peut la
          réinitialiser.
        </p>
      )}

      {enabled && !required && (
        <form className="mfa-setup" onSubmit={disable}>
          <p className="small muted">Pour désactiver la double authentification, confirmez avec un code de l&apos;application.</p>
          {codeField}
          <div className="admin-form-actions">
            <button type="submit" className="admin-btn" disabled={busy || code.replace(/\s/g, "").length !== 6}>
              Désactiver
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
