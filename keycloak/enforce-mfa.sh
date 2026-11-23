#!/usr/bin/env sh
# Impose la double authentification (TOTP) aux comptes qui écrivent dans le registre ou l'administrent.
# Le flux « browser » par défaut demande ensuite le code à chaque connexion de ces comptes.
# Usage : sh keycloak/enforce-mfa.sh   (conteneur docker compose « keycloak » démarré)
set -eu
export MSYS_NO_PATHCONV=1  # Git Bash sous Windows : ne pas réécrire les chemins du conteneur
KC="docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh"
$KC config credentials --server http://localhost:8080 --realm master --user admin --password admin >/dev/null
for role in validateur responsable-reglementaire responsable-produit administrateur-fonctionnel administrateur-technique; do
  for id in $($KC get "roles/$role/users" -r recallpharma --fields id --format csv --noquotes); do
    $KC update "users/$id" -r recallpharma -s 'requiredActions=["CONFIGURE_TOTP"]'
    echo "TOTP exigé : $role $id"
  done
done
