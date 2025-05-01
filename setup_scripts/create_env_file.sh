terraform -chdir=infra output -json | jq -r 'to_entries | .[] | "export \(.key | ascii_upcase)=\"\(.value.value)\""' >terraform_env.sh

echo "run source terraform_env.sh"
