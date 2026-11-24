# RecallPharma

Référentiel du médicament vétérinaire intégré à RecallVET. Pour un produit, un pays et une date, il indique :
- si le produit est autorisé ;
- ce que dit son RCP ;
- quel délai d'attente s'applique ;
- s'il fait l'objet d'une alerte.

Chaque réponse est accompagnée de sa preuve. Le dossier de conception unifié fait référence : https://claude.ai/artifact/MJVeJRHVBkE5VxFat8uxkb

## État : incréments 1 à 5 (phase 1, lots 2 et 3)

| Brique | Contenu | Règles |
|---|---|---|
| Moteur de règles (`backend/src/recallpharma/domain`) | Statut calculé de l'AMM, échéance calculée, niveau de preuve A–D, mentions de revérification, bandeaux, délais d'attente, teneurs, vérification de lot ; fonctions pures, sans horloge ni base | RG-03 à RG-08, RG-11, RG-13 à RG-16, RG-19 à RG-22, RG-31 |
| Base (`backend/migrations`) | PostgreSQL 17 : schémas `reg` et `integration`, recherche sans accents et tolérante aux fautes (pg_trgm, unaccent), événements et audit en ajout seul, journal d'audit chaîné SHA-256 | RG-01, RG-08, RG-15, RG-33 |
| API (`backend/src/recallpharma/api`) | `/v1/search`, `/v1/authorisations/{id}` (fiche, `as_of` et `known_at`), `/v1/authorisations/{id}/withdrawal-end`, `/v1/alerts`, `/v1/batch-check`, erreurs RFC 9457 | RG-05, RG-06, RG-16, RG-18, RG-21, RG-22 |
| Circuit de validation (`domain/curation.py`, `curation/`, `/v1/curation/*`) | Dépôt de documents sources (SHA-256, doublon refusé, versions chaînées) ; proposition → première validation champ par champ (page source affichée obligatoire) → ressaisie à l'aveugle → publication atomique, ou litige → arbitrage motivé ; toute modification après signature remet la revue à zéro ; historique et audit en ajout seul | RG-01, RG-07, RG-09 à RG-12, RG-32, RG-33 |
| Interface web (`web/`) | Next.js, qui sert aussi de BFF : recherche, fiche en cinq vues avec calcul du délai d'attente et vérification de lot, alertes ; back-office de validation (documents, saisie, première validation, ressaisie à l'aveugle, arbitrage) ; parcours Playwright de bout en bout | Toutes celles ci-dessus, à l'écran |
| Comptes et rôles (`keycloak/`, `api/auth.py`, `web/src/lib/oidc.ts`) | Keycloak 26 : royaume `recallpharma` (13 rôles, 15 comptes fictifs) ; le BFF se connecte en code d'autorisation avec PKCE et garde les jetons dans un cookie chiffré (AES-GCM), renouvelés par le middleware ; l'API vérifie chaque jeton (signature, émetteur, audience, expiration) et applique les rôles du jeton, recopiés et audités dans le compte ; double authentification TOTP imposable aux comptes du back-office | RG-32, RG-33 |
| Copilot (`domain/copilot.py`, `domain/selection.py`, `gateway/`, `api/copilot*.py`, `web/…/copilote`) | Passerelle d'IA séparée, sans accès à la base : le modèle open source choisit les outils, puis rédige des phrases de liaison faites de références `[[enregistrement:champ]]` ; la passerelle insère les valeurs, compose les bandeaux et le tableau, puis contrôle la réponse (aucun chiffre ni terme réservé hors référence), avec repli sur le tableau seul en cas d'échec. Les outils sont des points d'accès de lecture servis à un jeton délégué de 5 minutes, refusé partout ailleurs. Flux d'événements (le tableau arrive avant le texte), quotas, journal reconstituable, masquage, signalement d'erreur, effacement | RG-15, RG-16, RG-23 à RG-27 |
| Jeu de démonstration | Annexe A10 : 60 AMM fictives et leurs résultats attendus, rejoués par les tests | — |

Les données sont **entièrement fictives** (annexe A10). Aucune AMM réelle n'est chargée tant que la convention avec le MINEPIA n'est pas signée.

## Démarrer

Prérequis : Docker et [uv](https://docs.astral.sh/uv/).

```sh
docker compose up -d                      # PostgreSQL 17 + pgvector (port 5434) et Keycloak (port 8280)
cd backend
uv sync
uv run alembic upgrade head               # schéma
uv run python -m recallpharma.seed.load_db   # jeu fictif A10
RECALLPHARMA_REFERENCE_DATE=2027-09-07 uv run uvicorn recallpharma.api.app:app --reload
```

Interface web, dans un second terminal :

```sh
cd web
pnpm install
RECALLPHARMA_API_URL=http://127.0.0.1:8000 pnpm dev   # http://localhost:3000
```

Keycloak importe le royaume au premier démarrage (console : http://localhost:8280, `admin` / `admin`). Tous les comptes fictifs ont le mot de passe `demo-recallpharma` ; leurs identifiants sont listés sur la page `/connexion`.

`RECALLPHARMA_REFERENCE_DATE` fige la date de consultation à celle du jeu A10. Sans elle, les statuts sont calculés à la date du jour.

La documentation interactive de l'API est servie sur http://localhost:8000/docs.

## Circuit de validation

On se connecte par Keycloak. L'API attend un jeton `Authorization: Bearer` émis par le royaume `recallpharma` pour l'audience `recallpharma-api` ; les rôles du jeton font foi, et les contrôles restent ceux du domaine. Le mode `RECALLPHARMA_AUTH_MODE=dev` (compte désigné par l'en-tête `X-RecallPharma-User`) ne sert qu'aux tests automatiques. Comptes du jeu A10 :

| Rôle dans le circuit | Compte | Rôle du compte |
|---|---|---|
| A, préparateur | `cpt-06` (`demo06@recallpharma.example`) | Validateur |
| B, premier validateur | `cpt-13` | Validateur |
| C, second validateur à l'aveugle | `cpt-07` | Responsable réglementaire |
| Arbitre (aucun des trois précédents) | `cpt-15` | Responsable réglementaire |
| Refusé partout (RG-32) | `cpt-10` | Administrateur technique |

| Étape | Appel |
|---|---|
| Déposer le document source | `POST /v1/curation/documents` (multipart) |
| Créer une proposition | `POST /v1/curation/proposals`, ou `POST /v1/curation/authorisations/{id}/proposals` pour mettre à jour une AMM publiée |
| Citer les sources, corriger | `PUT /v1/curation/proposals/{id}` (avec `expected_revision`) |
| Soumettre | `POST …/submit` (bloqué si un champ critique est vide, sans source ou à teneur ambiguë) |
| B affiche chaque source puis valide | `POST …/fields/{champ}/source-view`, puis `POST …/first-validation` |
| C ressaisit à l'aveugle | `GET …/blind-entry`, puis `POST …/blind-entry` → `publiée` ou `en litige` |
| Arbitrage motivé | `POST …/arbitration` (`retenir la préparation`, `retenir la ressaisie` ou `rejeter`) |

## Contrôles

```sh
uv run pytest            # 167 tests ; ceux de l'API créent une base recallpharma_test par module
uv run ruff check . && uv run ruff format --check .
uv run mypy              # typage strict
uv run lint-imports      # le domaine ne dépend ni de FastAPI, ni de SQLAlchemy, ni de Pydantic
```

## Choix à faire valider

- **Délai en jours (RG-21)** : « arrondi au début du jour suivant » est lu comme minuit du jour qui suit l'instant atteint, même si cet instant tombe déjà à minuit. C'est le choix le plus prudent. À confirmer par le pharmacien réglementaire.
- **Rappel de lot clos** : il continue de viser ses lots. La réponse reste « lot visé par un rappel publié » (RG-22).
- **Niveau A** : il exige aussi deux validations (RG-14). Une seule validation plafonne la donnée au niveau B.
- **Bitemporalité** : elle porte sur les événements réglementaires (`recorded_at`). Pour les autres champs, l'historique est assuré par les propositions archivées, les versions successives du RCP et le journal d'audit (avant et après). Le versionnement des colonnes de l'AMM, au sens de `as_of` et `known_at`, reste à faire.
- **Arbitrage (RG-11)** : tout responsable réglementaire ou responsable produit peut arbitrer, à condition de n'être ni A, ni B, ni C.
- **Mise à jour d'une AMM publiée** : les sources doivent être citées à nouveau, et B doit réafficher chaque page.

## Double authentification

Le royaume de développement ne l'impose pas, pour que les démonstrations et les tests restent simples. Pour l'exiger des comptes qui écrivent ou administrent (Validateur, Responsable réglementaire, Responsable produit, administrateurs) :

```sh
sh keycloak/enforce-mfa.sh   # chaque compte configure son TOTP à la connexion suivante
```

Le royaume est généré à partir du jeu A10 par `keycloak/generate_realm.py`. Il n'est destiné qu'au développement : mot de passe commun, secret client connu, administrateur `admin`. En production, le secret client (`RECALLPHARMA_OIDC_CLIENT_SECRET`) et la clé de session (`RECALLPHARMA_SESSION_SECRET`) sont obligatoires.

## Copilot

Le modèle est un modèle open source (licence Apache 2.0) servi par une interface compatible OpenAI : vLLM en production, Ollama sur le poste de développement. Par défaut, c'est Qwen2.5 7B Instruct, en attendant le modèle affiné sur nos données.

```sh
docker compose --profile ia up -d ollama
docker compose exec ollama ollama pull qwen2.5:7b-instruct           # 4,7 Go
cd backend
RECALLPHARMA_REFERENCE_DATE=2027-09-07 uv run uvicorn recallpharma.gateway.app:app --port 8001   # passerelle d'IA
uv run python -m recallpharma.evaluation.copilot_eval                # jeu de référence, métriques CT-IA-01
```

Variables : `RECALLPHARMA_LLM_BASE_URL` (défaut `http://localhost:11434/v1`), `RECALLPHARMA_LLM_MODEL`, `RECALLPHARMA_LLM_API_KEY`, `RECALLPHARMA_GATEWAY_URL` (vu de l'API), `RECALLPHARMA_API_URL` (vu de la passerelle), `RECALLPHARMA_COPILOT_TOKEN_SECRET` (obligatoire hors développement).

Ce qui est garanti par construction, et testé sans modèle (modèle scénarisé, `tests/api/test_copilot_api.py`) :
- **Valeurs :** toute valeur affichée vient d'un résultat d'outil du tour. Une rédaction qui écrit elle-même un chiffre, une substance, une espèce ou un statut est refusée ; après deux refus, seul le tableau s'affiche.
- **Décomptes :** ils viennent du registre. Un affinage est un appel d'outil sur le jeu de résultats précédent, et les délais non comparables sont listés à part.
- **Abstentions :** le Copilot s'abstient sans appeler le modèle pour un diagnostic, un choix de traitement ou un médicament humain. Il s'abstient aussi pour un produit absent, une juridiction non couverte ou des données de niveau D uniquement.
- **Bandeaux :** ils sont composés sans le modèle et envoyés avant le texte (RG-15). Une AMM autorisée seulement ailleurs est étiquetée comme telle (RG-16).
- **Mentions :** chaque réponse porte la juridiction, la date de vérification la plus ancienne, le niveau de preuve le plus faible et la mention de non-substitution (RG-26).
- **Écriture :** aucun outil n'écrit. Le jeton délégué reçoit une erreur 403 hors des outils, et les tentatives d'injection sont notées au journal.

Ce que les tests ne garantissent pas : que le modèle désigne le bon enregistrement pour la question posée. Ce risque se mesure avec le jeu de référence (`evaluation/copilot-reference.json`, 10 questions ; le jeu de recette en prévoit 300, puis 600).

Premier passage avec le vrai modèle (Qwen2.5 7B Instruct sous Ollama, processeur seul, rapport dans `backend/evaluation-results/`) :
- **Résultats :** 10 questions sur 10 exactes, toutes les abstentions correctes et aucune réponse rédigée refusée par le contrôle.
- **Échantillon :** 10 questions donnent un intervalle de confiance large (72 % à 100 % pour l'exactitude) ; le seuil de recette se juge sur 300 questions.
- **Corrections apportées par ce passage :** le contrôle reconnaît maintenant les accords et les formes anglaises (« suspendu », « bovines », « ivermectin »). La passerelle ignore une abstention demandée après obtention de données, et ne rejoue pas un appel d'outil identique.
- **Durée :** 2 à 5 minutes par réponse sur ce poste, contre une cible de 15 s qui suppose un serveur à carte graphique (vLLM).
- **Point restant :** les noms d'espèces en anglais (« cattle ») ne figurent pas dans les listes fermées.

Écarts assumés du prototype :
- **Jeton délégué :** l'API l'émet elle-même. L'échange de jeton RFC 8693 de Keycloak, prévu par l'ADR-08, le remplacera sans changer les points d'accès.
- **Recherche dans les RCP :** les outils `search_spc_passages` (recherche hybride, pgvector) et `compare_jurisdictions` restent à faire.
- **Masquage :** les noms de personnes ne sont pas encore masqués dans les questions enregistrées.
- **Durée de réponse :** sur un processeur sans carte graphique, le modèle 7B dépasse le délai cible de 15 s.

## Suite prévue

1. Affinage du modèle (LoRA/QLoRA puis DPO) sur les échanges relus, et recherche dans les RCP (pgvector).
2. Affichage de la page source (PDF) dans l'écran de première validation.
