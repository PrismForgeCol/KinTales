#!/usr/bin/env bash
# KinTales Dev Stack Stopper

echo "Stopping KinTales Backend and Frontend..."
pkill -f "main:app.*8001" 2>/dev/null
pkill -f "http.server 3000" 2>/dev/null
echo "KinTales services stopped."
