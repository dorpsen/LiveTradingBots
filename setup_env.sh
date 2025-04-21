#!/bin/bash

# setup_env.sh
# Description: Sets up the Python environment for the trading bot project on Fedora.
# Usage: Run from the project root directory: ./setup_env.sh

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Trading Bot Environment Setup for Fedora ---"

# --- Configuration ---
VENV_DIR=".venv" # Name of the virtual environment directory
PYTHON_CMD="python3" # Command to use for Python 3
REQ_FILE="requirements.txt"
REQ_DEV_FILE="requirements-dev.txt" # Optional: for pytest, etc.

# --- System Dependencies ---
echo "[1/4] Checking/Installing system build dependencies (requires sudo)..."
# Needed for building some Python packages (e.g., those with C extensions)
sudo dnf install -y gcc python3-devel redhat-rpm-config || {
    echo "Error: Failed to install system dependencies with dnf."
    exit 1
}
echo "System dependencies checked/installed."

# --- Python Check ---
echo "[2/4] Checking for Python 3..."
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "Error: $PYTHON_CMD could not be found. Please install Python 3."
    exit 1
fi
echo "Found Python 3: $($PYTHON_CMD --version)"

# --- Virtual Environment ---
echo "[3/4] Setting up Python virtual environment in '$VENV_DIR'..."
if [ ! -d "$VENV_DIR" ]; then
    $PYTHON_CMD -m venv $VENV_DIR
    echo "Virtual environment created."
else
    echo "Virtual environment '$VENV_DIR' already exists."
fi

# Activate script path (adjust if needed, but we'll call pip directly)
PYTHON_IN_VENV="$VENV_DIR/bin/python"
PIP_IN_VENV="$VENV_DIR/bin/pip"

# --- Install Python Packages ---
echo "[4/4] Installing Python packages from $REQ_FILE..."
if [ ! -f "$REQ_FILE" ]; then
    echo "Error: $REQ_FILE not found in the current directory."
    echo "Please ensure you are running this script from the project root."
    exit 1
fi

$PIP_IN_VENV install --upgrade pip
$PIP_IN_VENV install -r $REQ_FILE

# Optional: Install development dependencies
if [ -f "$REQ_DEV_FILE" ]; then
    echo "Installing development packages from $REQ_DEV_FILE..."
    $PIP_IN_VENV install -r $REQ_DEV_FILE
else
    echo "No $REQ_DEV_FILE found, skipping development dependencies."
fi

echo "Python packages installed."

echo "--- Setup Complete ---"
echo "To activate the virtual environment, run:"
echo "source $VENV_DIR/bin/activate"
echo "----------------------"

exit 0
