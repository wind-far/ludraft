#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker build -t gamedev-runner:1 runner
