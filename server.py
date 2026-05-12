#!/usr/bin/env python3
"""
Simple Flask server for Railway deployment
"""
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/')
def home():
    return jsonify({
        "message": "ClipForge License Server",
        "status": "running"
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
