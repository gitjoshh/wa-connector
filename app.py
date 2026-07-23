from flask import Flask, request, jsonify
import os
import requests
import json
from datetime import datetime

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'my_verify_token')
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN', '')


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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
