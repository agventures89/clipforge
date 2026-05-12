#!/usr/bin/env python3
"""
ClipForge AI - Gumroad Webhook Handler
========================================
Automatically generates and emails license keys when someone buys on Gumroad.

SETUP:
1. Deploy this alongside license_server.py on Railway
2. In Gumroad Settings → Advanced → Webhooks, add:
   https://your-railway-url.up.railway.app/gumroad-webhook

3. Set environment variables:
   GUMROAD_WEBHOOK_SECRET=your-gumroad-ping-secret
   LICENSE_SECRET=same-as-license-server
   EMAIL_API_KEY=your-sendgrid-or-resend-api-key

FLOW:
  Buyer purchases → Gumroad webhook fires → This script:
  1. Verifies webhook signature
  2. Generates license key via license_server
  3. Sends welcome email with key
  4. Logs purchase to database
"""

import os, json, hmac, hashlib
from flask import Flask, request, jsonify
from datetime import datetime
import subprocess

app = Flask(__name__)

# Environment variables
GUMROAD_SECRET = os.getenv("GUMROAD_WEBHOOK_SECRET", "")
LICENSE_SECRET = os.getenv("LICENSE_SECRET", "")
EMAIL_API_KEY = os.getenv("EMAIL_API_KEY", "")

def verify_gumroad_signature(payload, signature):
    """Verify webhook came from Gumroad"""
    if not GUMROAD_SECRET:
        return True  # Skip verification in dev mode
    
    expected = hmac.new(
        GUMROAD_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)

def generate_license_key(plan, email):
    """Call license_server.py to generate a key"""
    try:
        result = subprocess.run(
            ["python3", "license_server.py", "generate", 
             "--plan", plan, "--email", email],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # Extract license key from output
            for line in result.stdout.split('\n'):
                if line.startswith("CFAI-"):
                    return line.strip()
        
        return None
    except Exception as e:
        print(f"Error generating license: {e}")
        return None

def send_welcome_email(email, license_key, plan, product_name):
    """Send email with license key using Resend API"""
    import requests
    
    if not EMAIL_API_KEY:
        print(f"Would email {email} with key {license_key}")
        return True
    
    # Email templates by plan
    templates = {
        "monthly": {
            "subject": "Welcome to ClipForge AI - Your License Key Inside",
            "body": f"""
Hi there!

Your ClipForge AI Monthly license is now active. Here's everything you need:

LICENSE KEY: {license_key}

DOWNLOAD:
https://download.clipforgeai.com?key={license_key}

NEXT STEPS:
1. Download and install ClipForge AI
2. Enter your license key when prompted
3. Get your Anthropic API key at console.anthropic.com
4. Process your first video in under 10 minutes

Your setup guide is attached to this email.

Questions? Reply to this email or contact support@clipforgeai.com

Welcome to the team,
ClipForge AI
"""
        },
        "solo": {
            "subject": "ClipForge AI Solo - You Saved $85! License Key Inside",
            "body": f"""
Hi there!

Smart choice - you just saved $85 on your 6-month ClipForge AI license!

LICENSE KEY: {license_key}
PLAN: 6-Month Solo ($497 / 6 months = $82.83/month)

DOWNLOAD:
https://download.clipforgeai.com?key={license_key}

PRIORITY SUPPORT:
As a Solo plan member, you get priority email support with 24-hour response times.
Just email support@clipforgeai.com with PRIORITY in the subject line.

NEXT STEPS:
1. Download and install ClipForge AI
2. Enter your license key when prompted
3. Get your Anthropic API key at console.anthropic.com
4. Process your first video in under 10 minutes

Your setup guide is attached to this email.

Your subscription renews automatically in 6 months at $497. Cancel anytime from your Gumroad library.

Questions? support@clipforgeai.com

Welcome to ClipForge AI,
The ClipForge Team
"""
        },
        "team": {
            "subject": "ClipForge AI Team - You Saved $749! Activate Your Team",
            "body": f"""
Hi there!

Your ClipForge AI Team license is now active. You saved $749!

PRIMARY LICENSE KEY: {license_key}
PLAN: 6-Month Team (Up to 3 users)

DOWNLOAD:
https://download.clipforgeai.com?key={license_key}

ACTIVATING TEAM SEATS:
Your primary key is ready to use. To activate your 2 additional team seats:

1. Forward this email to support@clipforgeai.com
2. Include the email addresses of your 2 team members
3. We'll generate their license keys within 12 hours

PRIORITY SUPPORT:
Team plan members get 12-hour priority support.
Email support@clipforgeai.com with PRIORITY in the subject.

NEXT STEPS:
1. Download and install ClipForge AI
2. Enter your license key when prompted
3. Get your Anthropic API key at console.anthropic.com
4. Process your first video in under 10 minutes

Your setup guide is attached to this email.

Your subscription renews automatically in 6 months at $997. Cancel anytime from your Gumroad library.

Questions? support@clipforgeai.com

Welcome to ClipForge AI,
The ClipForge Team
"""
        }
    }
    
    template = templates.get(plan, templates["monthly"])
    
    # Send via Resend API
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {EMAIL_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from": "ClipForge AI <hello@clipforgeai.com>",
            "to": [email],
            "subject": template["subject"],
            "text": template["body"]
        }
    )
    
    return response.status_code == 200

def map_product_to_plan(product_name, product_id):
    """Map Gumroad product name/ID to license plan"""
    product_lower = product_name.lower()
    
    if "team" in product_lower:
        return "team"
    elif "solo" in product_lower or "6-month" in product_lower:
        return "solo"
    elif "monthly" in product_lower or "month" in product_lower:
        return "monthly"
    
    # Default to monthly if unclear
    return "monthly"

@app.route('/gumroad-webhook', methods=['POST'])
def gumroad_webhook():
    """
    Receive webhook from Gumroad on new purchase
    
    Gumroad sends:
    {
      "seller_id": "xxx",
      "product_id": "xxx",
      "product_name": "ClipForge AI - 6-Month Solo",
      "permalink": "clipforge-solo",
      "email": "buyer@email.com",
      "price": "497",
      "gumroad_fee": "50",
      "currency": "usd",
      "sale_id": "xxx",
      "sale_timestamp": "2025-01-15T10:30:00Z",
      "license_key": "xxx",  # If you enabled Gumroad's license keys
      "subscription_id": "xxx",  # For recurring
      "is_gift_receiver_purchase": false,
      "refunded": false,
      "disputed": false,
      "dispute_won": false
    }
    """
    
    # Verify signature
    signature = request.headers.get('X-Gumroad-Signature', '')
    payload = request.get_data(as_text=True)
    
    if not verify_gumroad_signature(payload, signature):
        return jsonify({"error": "Invalid signature"}), 401
    
    data = request.json
    
    # Skip if refunded or disputed
    if data.get('refunded') or data.get('disputed'):
        return jsonify({"status": "skipped", "reason": "refunded or disputed"}), 200
    
    # Extract purchase details
    email = data.get('email')
    product_name = data.get('product_name', '')
    product_id = data.get('product_id', '')
    price = data.get('price', '')
    sale_id = data.get('sale_id', '')
    
    if not email:
        return jsonify({"error": "No email provided"}), 400
    
    # Map product to plan
    plan = map_product_to_plan(product_name, product_id)
    
    # Generate license key
    license_key = generate_license_key(plan, email)
    
    if not license_key:
        return jsonify({"error": "Failed to generate license key"}), 500
    
    # Send welcome email
    email_sent = send_welcome_email(email, license_key, plan, product_name)
    
    # Log the purchase
    log_purchase(sale_id, email, license_key, plan, price)
    
    return jsonify({
        "status": "success",
        "license_key": license_key,
        "plan": plan,
        "email_sent": email_sent
    }), 200

def log_purchase(sale_id, email, license_key, plan, price):
    """Log purchase to a simple JSON file"""
    log_file = "purchases.json"
    
    purchases = []
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            purchases = json.load(f)
    
    purchases.append({
        "sale_id": sale_id,
        "email": email,
        "license_key": license_key,
        "plan": plan,
        "price": price,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    with open(log_file, 'w') as f:
        json.dump(purchases, f, indent=2)

@app.route('/webhook-test', methods=['POST'])
def webhook_test():
    """Test endpoint to simulate Gumroad webhook"""
    data = request.json
    
    email = data.get('email', 'test@example.com')
    plan = data.get('plan', 'solo')
    
    license_key = generate_license_key(plan, email)
    email_sent = send_welcome_email(email, license_key, plan, f"ClipForge AI - {plan}")
    
    return jsonify({
        "license_key": license_key,
        "email_sent": email_sent
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    print("🚀 ClipForge Gumroad Webhook Handler")
    print("=" * 50)
    print(f"Gumroad secret: {'✓ set' if GUMROAD_SECRET else '✗ missing'}")
    print(f"License secret: {'✓ set' if LICENSE_SECRET else '✗ missing'}")
    print(f"Email API key:  {'✓ set' if EMAIL_API_KEY else '✗ missing'}")
    print()
    print("Add this webhook URL to Gumroad:")
    print("https://your-railway-url.up.railway.app/gumroad-webhook")
    print()
    
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))
