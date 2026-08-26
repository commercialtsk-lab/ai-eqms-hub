from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    VERIFY_TOKEN = "my_secret_token"
    
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            return "Verification failed", 403
    return "Hello World", 200

@app.route('/webhook', methods=['POST'])
def receive_message():
    data = request.json
    print("Received data:", data)
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
  
