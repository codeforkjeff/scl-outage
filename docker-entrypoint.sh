#!/usr/bin/env bash

uv run gunicorn --bind 0.0.0.0 --workers 2 scl_outage
