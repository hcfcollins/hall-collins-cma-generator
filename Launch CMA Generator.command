#!/bin/bash

# Hall Collins CMA Generator - Web App Launcher
# Double-click this file to start the CMA Generator in your browser

echo "🏡 Hall Collins CMA Generator"
echo "=================================="
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Check if app.py exists
if [ ! -f "app.py" ]; then
    echo "❌ ERROR: app.py not found!"
    echo "Make sure this script is in the CMA-Generator folder."
    read -p "Press Enter to close..."
    exit 1
fi

# Install/check requirements
echo "🔍 Checking dependencies..."
if command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt -q
elif command -v pip &> /dev/null; then
    pip install -r requirements.txt -q
fi

# Check Streamlit
if ! command -v streamlit &> /dev/null; then
    echo "❌ Streamlit not found. Installing..."
    pip3 install streamlit
fi

echo ""
echo "🚀 Starting Hall Collins CMA Generator..."
echo ""
echo "📱 Opening in your browser at:"
echo "   http://localhost:8502"
echo ""
echo "⏹️  To stop: Press Ctrl+C in this window, or just close it."
echo ""

# Launch on port 8502 so it doesn't conflict with the Listing Packet app (8501)
streamlit run app.py --server.port 8502

echo ""
echo "CMA Generator stopped."
read -p "Press Enter to close this window..."
