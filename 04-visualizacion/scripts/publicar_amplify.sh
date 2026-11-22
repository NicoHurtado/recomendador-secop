#!/usr/bin/env bash
# Publica la web en AWS Amplify Hosting (app "proyecto-integrador-secop", rama main).
# Link: https://main.d360gidrarcxt9.amplifyapp.com
# Uso (desde web/):  aws login --profile secop --region us-east-1   y luego   ./scripts/publicar_amplify.sh
# La app ya tiene dos reglas (no hay que tocarlas):
#   /api/<*>  -> https://i5rev77icbkeissqixiw6h5soi0npkxh.lambda-url.us-east-1.on.aws/<*>  (200, proxy: sin CORS)
#   rutas de la SPA -> /index.html (200)
set -euo pipefail
cd "$(dirname "$0")/.."
export AWS_PROFILE="${AWS_PROFILE:-secop}" AWS_REGION="${AWS_REGION:-us-east-1}"
APP_ID="${AMPLIFY_APP_ID:-d360gidrarcxt9}"
RAMA="${AMPLIFY_RAMA:-main}"

npm ci
npm run lint
npm test
npm run build

ZIP="$(mktemp -d)/dist.zip"
(cd dist && zip -qr -X "$ZIP" . -x '.DS_Store' '*/.DS_Store')

OUT=$(aws amplify create-deployment --app-id "$APP_ID" --branch-name "$RAMA" --output json)
JOB=$(echo "$OUT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["jobId"])')
URL=$(echo "$OUT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["zipUploadUrl"])')
curl -s -f -X PUT -H "Content-Type: application/zip" --data-binary @"$ZIP" "$URL" -o /dev/null
aws amplify start-deployment --app-id "$APP_ID" --branch-name "$RAMA" --job-id "$JOB" >/dev/null

for _ in $(seq 1 60); do
  S=$(aws amplify get-job --app-id "$APP_ID" --branch-name "$RAMA" --job-id "$JOB" --query 'job.summary.status' --output text)
  echo "Despliegue $JOB: $S"
  [[ $S == SUCCEED ]] && { echo "Listo: https://${RAMA}.${APP_ID}.amplifyapp.com"; exit 0; }
  [[ $S == FAILED || $S == CANCELLED ]] && exit 1
  sleep 5
done
