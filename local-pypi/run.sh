#!/usr/bin/env bash
set -e

docker run -t -i --rm \
    -h pypu.local \
    -v $HOME/.local/share/broccoli-local-pypi/srv/pypi:/srv/pypi:rw \
    -p 8080:80 \
    --name broccoli-local-pypi \
    codekoala/pypi
