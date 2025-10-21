#!/bin/bash
set -e
pip3 install -r /var/local/ralph/requirements/dev.txt
cd /var/local/ralph
/opt/local/rebuild-local-dev-statics.sh
make run
