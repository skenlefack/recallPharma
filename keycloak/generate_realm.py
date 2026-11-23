"""Génère le royaume Keycloak de développement à partir des comptes fictifs du jeu A10.

Usage (depuis la racine) : backend/.venv/Scripts/python keycloak/generate_realm.py
Comptes de démonstration uniquement : mot de passe commun, secret client connu. Ne jamais importer en production.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from recallpharma.api.auth import ROLE_SLUGS  # noqa: E402

WEB_ORIGINS = ["http://localhost:3100", "http://localhost:3000"]
label_to_slug = {label: slug for slug, label in ROLE_SLUGS.items()}
seed = json.loads((ROOT / "backend/src/recallpharma/seed/A10-jeu-amorcage.json").read_text(encoding="utf-8"))

users = [
    {
        "username": a["login"],
        "email": a["login"],
        "emailVerified": True,
        "enabled": True,
        "firstName": a["role"],
        "lastName": a["id"],
        "credentials": [{"type": "password", "value": "demo-recallpharma", "temporary": False}],
        "realmRoles": ["default-roles-recallpharma", label_to_slug[a["role"]]],
    }
    for a in seed["accounts"]
]

realm = {
    "realm": "recallpharma",
    "enabled": True,
    "displayName": "RecallPharma (développement)",
    "internationalizationEnabled": True,
    "supportedLocales": ["fr", "en"],
    "defaultLocale": "fr",
    "sslRequired": "external",
    "registrationAllowed": False,
    "loginWithEmailAllowed": True,
    "bruteForceProtected": True,
    "failureFactor": 5,
    "accessTokenLifespan": 300,
    "ssoSessionIdleTimeout": 1800,
    "ssoSessionMaxLifespan": 28800,
    "otpPolicyType": "totp",
    "otpPolicyAlgorithm": "HmacSHA1",
    "otpPolicyDigits": 6,
    "otpPolicyPeriod": 30,
    "passwordPolicy": "length(12)",
    "roles": {"realm": [{"name": slug, "description": label} for slug, label in ROLE_SLUGS.items()]},
    "clients": [
        {
            "clientId": "recallpharma-api",
            "name": "API RecallPharma (audience des jetons)",
            "enabled": True,
            "bearerOnly": True,
            "publicClient": False,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
        },
        {
            "clientId": "recallpharma-web",
            "name": "Interface web RecallPharma (BFF)",
            "enabled": True,
            "publicClient": False,
            "clientAuthenticatorType": "client-secret",
            "secret": "dev-only-web-secret",
            "standardFlowEnabled": True,
            "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "serviceAccountsEnabled": False,
            "frontchannelLogout": True,
            "redirectUris": [f"{o}/api/auth/callback" for o in WEB_ORIGINS],
            "webOrigins": WEB_ORIGINS,
            "attributes": {
                "pkce.code.challenge.method": "S256",
                "post.logout.redirect.uris": "##".join(f"{o}/*" for o in WEB_ORIGINS),
            },
            "defaultClientScopes": ["roles", "profile", "email", "basic", "web-origins", "acr"],
            "optionalClientScopes": [],
            "protocolMappers": [
                {
                    "name": "audience recallpharma-api",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-audience-mapper",
                    "config": {
                        "included.client.audience": "recallpharma-api",
                        "access.token.claim": "true",
                        "id.token.claim": "false",
                        "introspection.token.claim": "true",
                    },
                }
            ],
        },
    ],
    "users": users,
}

out = ROOT / "keycloak" / "realm-recallpharma.json"
out.write_text(json.dumps(realm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"{out.relative_to(ROOT)} : {len(users)} comptes")
