"use client";

import { useState } from "react";

import { EyeIcon, EyeOffIcon, LockIcon } from "@/components/icons";

/** Champ mot de passe avec bouton afficher / masquer. */
export function PasswordField() {
  const [visible, setVisible] = useState(false);
  return (
    <div className="auth-input">
      <LockIcon size={18} />
      <input
        id="password"
        name="password"
        type={visible ? "text" : "password"}
        autoComplete="current-password"
        placeholder="Votre mot de passe"
        required
      />
      <button
        type="button"
        className="auth-eye"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
        aria-pressed={visible}
      >
        {visible ? <EyeOffIcon size={18} /> : <EyeIcon size={18} />}
      </button>
    </div>
  );
}
