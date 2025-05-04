#!/bin/bash

echo "--- Trading Bot Environment Setup ---"

# Function to check for the existence of a command
command_exists () {
  command -v "$1" >/dev/null 2>&1
}

# Detect the operating system
if command_exists apt-get; then
  OS="Ubuntu"
elif command_exists dnf; then
  OS="Fedora"
else
  echo "Error: Could not determine the operating system."
  exit 1
fi

echo "[1/4] Checking/Installing system build dependencies (requires sudo)..."

case "$OS" in
  "Ubuntu")
    echo "Detected Ubuntu. Installing build-essential and python3-dev..."
    sudo apt-get update
    sudo apt-get install -y build-essential python3-dev  # Or python-dev for Python 2
    if [ $? -ne 0 ]; then
      echo "Error: Failed to install system dependencies with apt."
      exit 1
    fi
    ;;
  "Fedora")
    echo "Detected Fedora. Installing development tools and python3-devel..."
    sudo dnf update -y
    sudo dnf install -y "@development-tools" python3-devel  # Or python-devel for Python 2
    if [ $? -ne 0 ]; then
      echo "Error: Failed to install system dependencies with dnf."
      exit 1
    fi
    ;;
  *)
    echo "Error: Unsupported operating system: $OS"
    exit 1
    ;;
esac

echo "[2/4] Checking/Creating virtual environment (if needed)..."
if ! command_exists python3; then
  echo "Error: Python 3 is not installed. Please install it manually."
  exit 1
fi

if ! command_exists virtualenv; then
  echo "Installing virtualenv..."
  pip3 install --no-cache-dir virtualenv
  if [ $? -ne 0 ]; then
    echo "Error: Failed to install virtualenv."
    exit 1
  fi
fi

if [ ! -d "venv" ]; then
  echo "Creating virtual environment 'venv'..."
  python3 -m venv venv
  if [ $? -ne 0 ]; then
    echo "Error: Failed to create virtual environment."
    exit 1
  fi
else
  echo "Virtual environment 'venv' already exists."
fi

echo "[3/4] Activating virtual environment and installing Python dependencies..."
source venv/bin/activate
pip3 install --no-cache-dir -r requirements.txt
deactivate

echo "[4/4] Environment setup complete!"
echo "You can now activate the virtual environment using: source venv/bin/activate"
echo "And run your trading bot."