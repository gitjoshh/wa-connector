from flask import Flask, request, jsonify
import os
import requests
import json
import hmac
from datetime import datetime

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'my_verify_token')
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN', '')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID', '')
WHATSAPP_API_TOKEN = os.environ.get('WHATSAPP_API_TOKEN', '')


@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Meta calls this to verify your webhook is real."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print('Webhook verified successfully.')
        return challenge, 200
    else:
        return 'Forbidden', 403


@app.route('/webhook', methods=['POST'])
def receive_message():
    """Meta sends incoming messages here."""
    data = request.json
    print(f"Incoming payload: {json.dumps(data, indent=2)}")

    if data.get('object') == 'whatsapp_business_account':
        for entry in data.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                messages = value.get('messages', [])

                for message in messages:
                    msg_type = message.get('type')
                    from_number = message.get('from')
                    timestamp = message.get('timestamp')

                    if msg_type == 'text':
                        text = message['text']['body']
                        log_message(from_number, 'text', text, timestamp)

                    elif msg_type == 'audio':
                        media_id = message['audio']['id']
                        log_message(from_number, 'voice_note', f'media_id:{media_id}', timestamp)
                        download_media(media_id, from_number, timestamp)

                    else:
                        log_message(from_number, msg_type, '[unsupported type]', timestamp)

    return jsonify({'status': 'ok'}), 200


def log_message(from_number, msg_type, content, timestamp):
    log_entry = {
        'from': from_number,
        'type': msg_type,
        'content': content,
        'timestamp': datetime.fromtimestamp(int(timestamp)).isoformat()
    }
    print(f"LOG: {json.dumps(log_entry)}")
    with open('messages.log', 'a') as f:
        f.write(json.dumps(log_entry) + '\n')


def download_media(media_id, from_number, timestamp):
    if not WHATSAPP_TOKEN:
        print("WHATSAPP_TOKEN not set — skipping voice note download.")
        return

    headers = {'Authorization': f'Bearer {WHATSAPP_TOKEN}'}

    # Step 1: get the media URL from its ID
    meta_response = requests.get(
        f'https://graph.facebook.com/v19.0/{media_id}',
        headers=headers
    )
    if meta_response.status_code != 200:
        print(f"Failed to get media URL: {meta_response.text}")
        return

    media_url = meta_response.json().get('url')

    # Step 2: download the actual audio file
    audio_response = requests.get(media_url, headers=headers)
    if audio_response.status_code == 200:
        filename = f"voice_{from_number}_{timestamp}.ogg"
        with open(filename, 'wb') as f:
            f.write(audio_response.content)
        print(f"Voice note saved: {filename}")
    else:
        print(f"Failed to download audio: {audio_response.text}")


def check_caller_auth():
    """Validates the caller's Authorization header against WHATSAPP_API_TOKEN."""
    auth_header = request.headers.get('Authorization', '')
    prefix = 'Bearer '
    token = auth_header[len(prefix):] if auth_header.startswith(prefix) else ''
    if not token or not hmac.compare_digest(token, WHATSAPP_API_TOKEN):
        return False
    return True


def send_to_meta(payload):
    """POSTs a message payload to the Meta Graph API and returns (status, body)."""
    headers = {
        'Authorization': f'Bearer {WHATSAPP_TOKEN}',
        'Content-Type': 'application/json'
    }
    meta_response = requests.post(
        f'https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages',
        headers=headers,
        json=payload
    )
    return meta_response


@app.route('/send', methods=['POST'])
def send_message():
    if not check_caller_auth():
        return jsonify({'status': 'error', 'detail': 'Unauthorized'}), 401

    data = request.json or {}
    to = data.get('to')
    message = data.get('message')
    if not to or not message:
        return jsonify({'status': 'error', 'detail': 'Missing required fields: to, message'}), 400

    payload = {
        'messaging_product': 'whatsapp',
        'to': to,
        'type': 'text',
        'text': {'body': message}
    }

    meta_response = send_to_meta(payload)
    if meta_response.status_code == 200:
        return jsonify({'status': 'sent', 'response': meta_response.json()}), 200
    else:
        return jsonify({'status': 'error', 'detail': meta_response.text}), meta_response.status_code


@app.route('/send-template', methods=['POST'])
def send_template_message():
    if not check_caller_auth():
        return jsonify({'status': 'error', 'detail': 'Unauthorized'}), 401

    data = request.json or {}
    to = data.get('to')
    template_name = data.get('template_name')
    language = data.get('language', 'en_US')
    params = data.get('params', [])
    if not to or not template_name or not params:
        return jsonify({'status': 'error', 'detail': 'Missing required fields: to, template_name, params'}), 400

    payload = {
        'messaging_product': 'whatsapp',
        'to': to,
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': language},
            'components': [
                {
                    'type': 'body',
                    'parameters': [{'type': 'text', 'text': params[0]}]
                }
            ]
        }
    }

    meta_response = send_to_meta(payload)
    if meta_response.status_code == 200:
        return jsonify({'status': 'sent', 'response': meta_response.json()}), 200
    else:
        return jsonify({'status': 'error', 'detail': meta_response.text}), meta_response.status_code


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
