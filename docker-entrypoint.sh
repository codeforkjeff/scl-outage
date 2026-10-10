#!/usr/bin/env bash

uv run hypercorn --bind 0.0.0.0:8000 scl_outage:app
