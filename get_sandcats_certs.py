#!/usr/bin/env python
__desc__ = "Fetch Sandstorm' Sandcat.io certificates"
__autor__ = "Juanjo Alvarez <juanjo@juanjoalvarez.net>"
__license__ = "MIT"

import os
import json
import shutil
from os.path import join, exists, isdir, splitext, split, sep

def parse_arguments():
    import argparse

    parser = argparse.ArgumentParser(description=__desc__)
    parser.add_argument('-x', '--lxd_certs_origin_dir', default=None,
            help='Origin directory in an LXD container. Use the syntax '
            'container_name/path/to/directory')
    parser.add_argument('-o', '--certs_origin_dir', default=None,
            help='Origin directory holding sandcats.io SSL certificate and private keys')
    parser.add_argument('-d', '--certs_dest_dir', default='/etc/nginx/ssl',
            help='Where to copy the SSL certificates')
    parser.add_argument('-k', '--key_filename', default='sandstorm.key',
            help='Default filename (without directory) for the private key file on the DESTINATION,\n'+
                 'DONT set this to the original Sandstorm private key!')
    parser.add_argument('-c', '--cert_filename', default='sandstorm.pem',
            help='Default filename (without directory) for the certificate file on the DESTINATION,\n'+
                 'DONT set this to the original Sandstorm certificate!')
    parser.add_argument('-r', '--restart_command', default='sudo systemctl restart nginx',
            help='Run this command to restart the reverse proxy. Set to "None" to handle it externally.')

    args = parser.parse_args()

    def printerror(msg):
        print('Error: {}'.format(msg))
        parser.print_help()
        exit(1)

    if sep in args.key_filename or sep in args.cert_filename:
        printerror('Dont use directories with -k or -c, just the filename!')

    if args.certs_origin_dir and not exists(args.certs_origin_dir):
        printerror('Specified directory for the Sandcats certificates doesnt exist')

    if not exists(args.certs_dest_dir):
        print('WARNING: The specified destination directory doesnt exist')

    return args


def get_cert_files(orig_dir, dest_dir):
    """
    Extract the latest certificate and key files from Sandstorm' sandcats directory
    and copy them to the configured destination (where you'll point your reverse
    proxy options for settings the cert files)
    """

    if not exists(orig_dir) or not isdir(orig_dir):
        print('ERROR: Configured Sandcats SSL directory doesnt exists or is not a dir')
        exit(1)

    if not exists(dest_dir) or not isdir(dest_dir):
        print('ERROR: Configured destination directory doesnt exists or is not a dir')
        exit(1)

    origfiles = (join(orig_dir, fn) for fn in os.listdir(orig_dir))
    origfiles = (path for path in origfiles if os.path.isfile(path))

    grouper = {}
    # Dict struct:
    # '123456': {'jsoncert': '/path/to/the/file/123456.response-json,
    #            'privkey' : '/path/to/the/file/123456}

    for f in origfiles:
        namepart = int(split(splitext(f)[0])[1])

        if f.endswith('.csr'):
            continue
        elif f.endswith('.response-json'):
            try:
                with open(f) as fp:
                    json.loads(fp.read())
            except Exception as e:
                print('WARNING: JSON file has wrong format, ignoring: %s (%s)' % (f, e))
                continue
            grouper.setdefault(namepart, {})['jsoncert'] = f
        elif '.' not in os.path.split(f)[1]:
            grouper.setdefault(namepart, {})['privkey'] = f

    # Now that we have the files nicely grouped by their namepart, get them sorted
    # by the most recent "oldest in the group" date
    cert_tuples = []
    for key, group in grouper.items():
        # filter out the single element groups
        if 'jsoncert' not in group or 'privkey' not in group:
            continue
        cert_tuples.append((int(key), group['jsoncert'], group['privkey']))

    if not cert_tuples:
        raise Exception('No valid certificate pair was found!')

    # Finally sort by tstamp (newest first) and get the first tuple
    cert_tuples.sort(key = lambda cert_tuples: cert_tuples[0], reverse = True)
    return cert_tuples[0][1:3]

def extract_cert(filepath):
    """
    Sandstorm gets the certificate and the CA as a json,
    this function extracts them to a single string with
    the CA first and the cert later
    """

    with open(filepath) as f:
        certjson = json.loads(f.read())

    if 'ca' in certjson and len(certjson['ca']) > 1:
        catext = '\n'.join(certjson['ca']).replace('\r\n', '\n')
        # catext = certjson['ca'][1].replace('\r\n', '\n')
    else:
        catext = None
    cert_text = certjson['cert'].replace('\r\n', '\n')

    return cert_text + '\n' + catext if catext else cert_text


def lxd_pull_files(lxd_dir):
    """
    Makes an 'lxc pull' of the certificates to a temporal directory
    and deletes that directory before finishing
    """

    from tempfile import mkdtemp
    import subprocess

    tmp_dir = mkdtemp()
    cmdlist = ['lxc', 'file', 'pull', '--recursive', lxd_dir, tmp_dir]
    subprocess.check_call(cmdlist)

    # Typically this will pull the directory user.sandcats.io, find the files
    # and move them to tmp_dir
    lfiles = os.listdir(tmp_dir)
    if len(lfiles) == 1:
        single_item = join(tmp_dir, lfiles[0])
        if isdir(single_item):
            subprocess.check_call('mv {}/* {}'.format(single_item, tmp_dir),
                                  shell = True)
            os.rmdir(single_item)

    return tmp_dir


def main():
    args = parse_arguments()

    if args.lxd_certs_origin_dir:
        origin_dir = lxd_pull_files(args.lxd_certs_origin_dir)
        delete_dir = True
    else:
        origin_dir = args.certs_origin_dir
        delete_dir = False

    try:
        certfile, privkey = get_cert_files(origin_dir,
                                          args.certs_dest_dir)
        cert_text = extract_cert(certfile)
        dest_file_cert = join(args.certs_dest_dir, args.cert_filename)
        dest_file_key  = join(args.certs_dest_dir, args.key_filename)

        # XXX crear directorio de destino si no existe

        if os.path.exists(dest_file_cert):
            # Dont overwrite if it didnt change
            with open(dest_file_cert) as d:
                text_orig = d.read().strip()

            if text_orig == cert_text.strip():
                exit(1)

        # Install the new certs
        print('Certificates changed, installing new certificates')
        with open(dest_file_cert, 'w') as pemfile:
            pemfile.write(cert_text)

        with open(dest_file_key, 'w') as keyfile:
            with open(privkey) as orig_key:
                key_text = orig_key.read()
            keyfile.write(key_text)
        if args.restart_command != 'None':
            subprocess.check_call(args.restart_command, shell = True)
    finally:
        if delete_dir:
            shutil.rmtree(origin_dir)


if __name__ == '__main__':
    main()
