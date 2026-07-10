#!/usr/bin/env bash
set -eu
pip install vulture 2>/dev/null
vulture src/automedia/ --min-confidence 80
