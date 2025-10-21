#!/bin/bash
set -e
cd /var/local/ralph
npm install
npm run build
python3 manage.py collectstatic --noinput
