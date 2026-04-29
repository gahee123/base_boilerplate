#!/bin/bash
set -e

# 1. Install kubectl if not present
if [ ! -f /usr/local/bin/kubectl ]; then
    echo "⏬ Downloading kubectl..."
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    chmod +x kubectl
    mv kubectl /usr/local/bin/kubectl
    echo "✅ kubectl installed."
fi

# 2. Check if cluster already exists
if kind get clusters | grep -q "^fastapi-test$"; then
    echo "🚀 Cluster 'fastapi-test' already exists."
else
    echo "🏗️ Creating kind cluster 'fastapi-test'..."
    kind create cluster --name fastapi-test
    echo "✅ Cluster created."
fi

echo "✨ All set! K8s environment is ready."
