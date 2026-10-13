#!/usr/bin/env bash
# Full refresh: pull from Planning Center, rebuild tables, analyze, render.
# Needs PCO_APP_ID and PCO_SECRET (Planning Center Personal Access Token) and
# network access to api.planningcenteronline.com.
set -euo pipefail
cd "$(dirname "$0")"
python3 fetch_pco.py "$@"
python3 build.py
python3 analyze.py
python3 render.py
