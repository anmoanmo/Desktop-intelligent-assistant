#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_NAME="${DESKTOP_ASSISTANT_CONDA_ENV:-desktop-assistant}"

if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda env update -n "$ENV_NAME" -f environment.yml --prune
else
  conda env create -n "$ENV_NAME" -f environment.yml
fi

echo "环境已准备完成。请执行：conda activate $ENV_NAME"
