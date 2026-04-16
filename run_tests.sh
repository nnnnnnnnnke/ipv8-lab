#!/bin/sh
cd "$(dirname "$0")"
exec python3 -m unittest discover -v -t . -s tests
