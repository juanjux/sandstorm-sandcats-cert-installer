## Sandstorm' sandcats.io integration script with a reverse proxy

This simple script could be useful if you have a [Sandstorm](https://sandstorm.io) installation with the Sandcats.io service enabled but you want to run it behing a reverse proxy like nginx. 

By default this is not obvious to do because:

- Sandcats.io certificates are only valid for the 443 port.

- Sandstorm need a wildcard domain or subdomain to run and letscrypt doesn't provide wildcard certificates. So to reverse proxy Sandstorm under your own domain you would need a paid wildcard cert (and those are not cheap) or run on unencrypted http (and you don't want that).

- Self signed wildcard certiciates work... more or less. Usually they make the images doesn't load correctly even if you accept the certificate (happened to me on Chrome, Opera, in Firefox grains wouldn't even load) or require you to create a rootCA cert and install it on every machine where you want to use Sandstorm. Which defeats the purpose of having web apps and it's not always easy to do on some phones or other non-PC devices.

The solution is to follow these steps:

#### Install and configure Sandstorm

Do the initial configuration of Sandstorm enabling the Sandcats service (so you get your free wildcard certificates).

#### Run this script

So you get those certs in your reverse proxy directory (for nginx this would tipically be `/etc/nginx/ssl`). Since Sancats.io certificates must be renewed weekly I suggest to add this to your cron. An example call could be:

```bash
python get_sandcats_certs.py --certs_origin_dir='/opt/sandstorm/var/sandcats/https' \
                             --certs_dest_dir='/etc/nginx/conf/ssl' \
                             --key_filename='sandstorm.key'
                             --dest_filename='sandstorm.pem'
```

#### Configure Sandstorm network

Configure Sandstorm to serve **unencripted HTTP** on any port that is not 443 and not accesible from the Internet. If you are [running Sandstorm on a Docker container](https://docs.sandstorm.io/en/latest/install/#option-6-using-sandstorm-within-docker) (like I do) just remove the `-p` parameter for the `docker run` command and add the port as a `--expose` like:

```bash
sudo docker run --name sandstorm \
        --privileged --sig-proxy=true --expose 6080 \
        -v /home/you/docker/sandstorm/data:/opt/sandstorm \
        -d buildpack-deps \
        bash -c 'useradd --system --user-group sandstorm && /opt/sandstorm/sandstorm start && tail -f /opt/sandstorm/var/log/sandstorm.log & sleep infinity'
```
If you use `--expose` only linked cointainers (like your reverse proxy container) will be able to see the port. If you're of the paranoid type like I'm you can also add a rule to your firewall blocking the port to outside connections.

If you are running it uncontained, edit the `/opt/sandstorm/sandstorm.conf` and change:

```
BIND_IP=0.0.0.0 
```

For:

```
BIND_IP=127.0.0.1
```

*(don't do this on containers - remember that every container with Docker has its own IP!).*

### Configure the reverse proxy

The reverse proxy will receive the HTTPS connections securely at the yourname.sandcats.io domain on the normal 443 port, using Sandstorm certificates and will proxy them to your Sandstorm service.

For example with nginx this should work:

```nginx
map $http_upgrade $connection_upgrade {
  default upgrade;
  ''      close;
}

server {
  server_name ~^(.*)>yourdomain\.sandcats\.io$ ~yourdomain\.sandcats\.io$;
  return 301 https://$host$request_uri;
}

server {
  listen 443 ssl;
  server_name ~^(.*)>yourdomain\.sandcats\.io$ ~yourdomain\.sandcats\.io$;

  ssl_certificate     /etc/nginx/ssl/sandstorm.pem;
  ssl_certificate_key /etc/nginx/ssl/sandstorm.key;
  include /etc/nginx/ssl_params.conf;

  client_max_body_size 10G; # change this value it according to $UPLOAD_MAX_SIZE

  location / {
    proxy_pass http://sandstorm:6080;
    include /etc/nginx/proxy_params;

    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
  }
}
```
Dont forget to point the ssl_certificate and the ssl_certificate_key to the directory where the script copied the certificates.

And after restarting Sandstorm and nginx this should work; at least it works perfectly for me, don't count on me for technical support, I don't work for Sandstorm.
