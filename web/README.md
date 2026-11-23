# RecallPharma — interface web

Next.js (App Router, TypeScript), rendu côté serveur. Le serveur Next.js sert aussi de BFF (ADR-04) :
- le navigateur n'appelle jamais l'API FastAPI directement ;
- les pages serveur interrogent l'API avec le jeton Keycloak de la session ;
- les actions du navigateur passent par `/api/bff/*`, qui refuse les requêtes venant d'une autre origine ;
- la connexion suit le flux OIDC code d'autorisation + PKCE (`/api/auth/login`, `/api/auth/callback`, `/api/auth/logout`) ;
- les jetons restent sur le serveur : le navigateur ne détient qu'un cookie `HttpOnly` chiffré (AES-GCM), et le middleware renouvelle le jeton d'accès avant son expiration.

| Page | Rôle |
|---|---|
| `/` | Recherche (nom, substance, n° d'AMM, titulaire), filtre par juridiction et par date |
| `/amm/[id]` | Fiche en cinq vues : identité, réglementation, RCP et délais (avec calculateur), preuves, alertes et vérification de lot |
| `/alertes` | Alertes publiées, filtrables par juridiction |
| `/copilote` | Copilot : questions sur le registre, réponse en flux (bandeaux et tableau d'abord, texte contrôlé ensuite), signalement d'erreur, effacement |
| `/connexion` | Connexion par Keycloak, déconnexion, liste des comptes fictifs du jeu A10 |
| `/validation` | Propositions classées par état, avec l'étape à faire selon le compte connecté |
| `/validation/documents` | Dépôt des documents sources (empreinte, versions) |
| `/validation/nouvelle`, `/validation/[id]` | Saisie (A), première validation avec affichage des sources (B), ressaisie à l'aveugle (C), arbitrage |

## Démarrer

Variables (valeurs par défaut adaptées au royaume de développement) : `RECALLPHARMA_API_URL`, `RECALLPHARMA_OIDC_ISSUER`, `RECALLPHARMA_OIDC_CLIENT_ID`, `RECALLPHARMA_OIDC_CLIENT_SECRET`, `RECALLPHARMA_SESSION_SECRET`.

```sh
pnpm install
RECALLPHARMA_API_URL=http://127.0.0.1:8000 pnpm dev   # API démarrée au préalable (voir ../README.md)
```

Après une modification de l'API, régénérer les types du contrat :

```sh
(cd ../backend && uv run python -m recallpharma.api.export_openapi ../web/openapi.json)
pnpm exec openapi-typescript openapi.json -o src/lib/api-types.ts
```

## Contrôles

```sh
pnpm exec tsc --noEmit && pnpm lint && pnpm build
pnpm exec playwright install chromium   # une fois
pnpm exec playwright test               # parcours de bout en bout ; Keycloak démarré, API sur :8000 avec RECALLPHARMA_REFERENCE_DATE=2027-09-07
```
