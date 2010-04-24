#! /usr/bin/env python

import sys
import urllib
try:
    import simplejson as json
except ImportError:
    import json

def fetch(sitehostname):
    url = 'http://%s/w/api.php?action=query&meta=siteinfo&siprop=general|namespaces|namespacealiases|magicwords|interwikimap&format=json' % sitehostname
    sys.stderr.write('fetching %r\n' % url)
    data = urllib.urlopen(url).read()
    data = json.loads(data)['query']
    return json.dumps(data, indent=4, sort_keys=True)

def main():
    argv = sys.argv
    if len(argv) < 2:
        sys.exit('Usage: %s SITEHOSTNAME' % argv[0])

    sitehostname = argv[1]
    serialized_data = fetch(sitehostname)
    sys.stdout.write(serialized_data)

if __name__ == '__main__':
    main()
