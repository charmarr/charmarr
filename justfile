# Justfile for running the Terraform modules' native tests.
#
# Usage:  just unit                 # run unit tests for every module under terraform/
#         just unit-test charmarr   # run unit tests for a single module

set quiet   # Recipes are silent by default
set export  # Just variables are exported to the environment

terraform := `which terraform || which tofu || echo ""` # require 'terraform' or 'opentofu'

[private]
default:
  just --list

# Run the unit tests for every Terraform module
[group("Unit")]
unit:
  #!/usr/bin/env bash
  set -euo pipefail
  if [ -z "${terraform}" ]; then echo "ERROR: please install terraform or opentofu"; exit 1; fi
  for dir in terraform/*/; do
    module="${dir#terraform/}"; module="${module%/}"
    [ -d "$dir/tests" ] || continue
    just --justfile {{justfile()}} unit-test "$module"
  done

# Run the unit tests for a single Terraform module
[group("Unit")]
[working-directory("./terraform")]
unit-test module:
  echo "==> Running unit tests for module: {{module}}"
  if [ -z "${terraform}" ]; then echo "ERROR: please install terraform or opentofu"; exit 1; fi
  $terraform -chdir={{module}} init -upgrade && $terraform -chdir={{module}} test
