"""Check anonymous JSON access plus browser-readable CORS after publication."""
import argparse
import json
import urllib.request
from urllib.parse import urlsplit
from price_index.dataset import validate_dataset


def check(url,origin):
    u=urlsplit(url)
    if u.scheme!='https' or u.username or u.password:raise ValueError('public HTTPS URL required')
    request=urllib.request.Request(url,headers={'Origin':origin,'Accept':'application/json'})
    # No Authorization or cookies supplied. Run from a normal unauthenticated
    # client too if your infrastructure injects origin authentication.
    with urllib.request.urlopen(request,timeout=20) as response:
        if response.headers.get('Access-Control-Allow-Origin') not in ('*',origin):
            raise ValueError('CORS header missing or wrong origin')
        if response.geturl()!=url:raise ValueError('redirected public URL; review destination')
        body=response.read(4_000_001)
        if len(body)>4_000_000:raise ValueError('response too large')
        validate_dataset(json.loads(body))
    print('Public JSON and CORS validation passed')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--origin',required=True,help='Your actual Blogger HTTPS origin')
    args=parser.parse_args()
    check(args.url,args.origin)
