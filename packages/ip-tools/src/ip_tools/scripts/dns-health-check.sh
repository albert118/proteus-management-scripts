#!/bin/bash

# DNS Health Check Script

DOMAIN="google.com"
EXPECTED_IP="93.184.216.34"
DNS_SERVER="8.8.8.8"
WEBHOOK_FILE="/root/discord-webhook-url.txt"

# Perform dig command
RESULT=$(dig @$DNS_SERVER $DOMAIN +short)

if [ "$RESULT" == "$EXPECTED_IP" ]; then
    echo "HEALTHY: $DOMAIN resolves to $RESULT"
else
    echo "UNHEALTHY: $DOMAIN resolves to $RESULT, expected $EXPECTED_IP"
    # notify on failure
    curl -H "Content-Type: application/json" \
     -X POST \
     -d '{"content": "**DNS health check failure**\n\nRepeated failures here mean this proxy has become unhealthy and requires attention."}' \
     $WEBHOOK_FILE
fi
