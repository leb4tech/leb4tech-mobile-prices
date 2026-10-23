"""Register the deployed Worker without placing tokens in logs or shell args."""
import json
import os
import sys
import urllib.request
from urllib.parse import urlsplit

def main():
    base=os.environ['BOT_WORKER_URL'].strip().rstrip('/')
    url=urlsplit(base)
    if url.scheme!='https' or not url.hostname or not url.hostname.endswith('.workers.dev') or url.path not in ('','/') or url.query or url.fragment or url.username or url.password:
        raise ValueError('invalid deployed workers.dev URL')
    token=os.environ['TELEGRAM_BOT_TOKEN']
    secret=os.environ['TELEGRAM_WEBHOOK_SECRET']
    # Telegram delivers updates serially; old queued updates are discarded at setup.
    payload={'url':base+'/telegram','secret_token':secret,'allowed_updates':['message','callback_query'],'max_connections':1,'drop_pending_updates':True}
    request=urllib.request.Request('https://api.telegram.org/bot'+token+'/setWebhook',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=30) as response:
        result=json.load(response)
    if result.get('ok') is not True:
        raise ValueError('Telegram webhook was not accepted')
    print('Telegram webhook registered. Open your bot and send /id, then configure TELEGRAM_OWNER_ID if needed.')

if __name__=='__main__':
    try:main()
    except Exception:
        # HTTP exceptions can include credential-bearing URLs: do not print them.
        print('Webhook setup failed; verify deployment URL and Telegram secrets.',file=sys.stderr)
        raise SystemExit(1)
