## Sandstorm' sandcats.io integration script with a reverse proxy

This simple script could be useful if you have a [Sandstorm](https://sandstorm.io) installation with the Sandcats.io service enabled but you want to run it behing a reverse proxy like nginx. 

By default this is not obvious to do because:

- Sandcats.io certificates are only valid for the 443 port.

- Sandstorm need a wildcard domain or subdomain to run and letscrypt doesn't provide wildcard certificates. So to reverse proxy Sandstorm under your own domain you would need a paid wildcard cert (and those are not cheap) or run on unencrypted http (and you don't want that).

- Self signed wildcard certiciates work... more or less. Usually they make the images doesn't load correctly even if you accept the certificate (happened to me on Chrome, Opera, in Firefox grains wouldn't even load) or require you to create a rootCA cert and install it on every machine where you want to use Sandstorm. Which defeats the purpose of having web apps and it's not always easy to do on some phones or other non-PC devices.

The [official documentation](https://docs.sandstorm.io/en/latest/administering/ssl/) advices to use [sniproxy](https://github.com/dlundquist/sniproxy) if you want to share the 443 port between your reverse proxy and your sandstorm installation. I did that for a while, having a dockerized sniproxy in front of both nginx and Sandstorm redirecting to the correct one based on the ssl handshake. I run like this for a while, but I had two problems. First, there was a noticeable performance penalty in requests/second compared to unproxied nginx. The second problem is that I saw that there was some leaking something between domains. For example using some web tool to analyze site performance that showed all requests I saw that, oddly, there were some requests of .js files that landed on my name.sandcats.io domain, and they delayed the page loading.

Finally after some tinkering and a little scripting I found a better and working solution. Follow these steps:

#### Install and configure Sandstorm

Do the initial installation and configuration of Sandstorm, choosing to enable the Sandcats service. Don't start the service yet. Now edit your `sandstorm.conf` file and configure it to also use HTTPS or uncommenting the line:

```bash
HTTPS_PORT=443
```

Its important to keep the port number of the `HTTPS_PORT` option at 443 on the since Sandcats.io certs only work for connections on this port. If you are running your Sandstorm service inside a Docker container you can leave this option enabled since this way the short-lived certificates will continue autorenewing themselves and you are not exporting the 443 port outside the container (see below) so it won't conflict with your reverse proxy.

If you aren't using Docker or some other virtualizing environment, probably you need to specify some other port and firewall it, but I don't know if this will work and will fetch the right certificates, or fetch them at all (if someone tries this please tell me). Another solution would be to briefly stop your reverse proxy and reenabling the HTTPS port on Sandstorm to let it fetch certificates when they expire. But this is not very elegant. 

Next step is to change the `BASE_URL` to use start with `https://` even if you have disabled the `HTTPS_PORT` setting, because thats the URL that will really be used to access the service once its running behind the reverse proxy (and OAUTH won't work if the URL is not this one).

```bash
# BASE_URL=http://yourname.sandcats.io
BASE_URL=https://yourname.sandcats.io
```

Then:

- Stop your reverse proxy so the 443 port is free
- Run the sandstorm service, making sure that the 443 port is accesible from the outside (unfirewall it, enable it on docker, whatever)
- Check with your browser that you can access your https URL
- Check the logs on `[sandstorm_dir]/data/var/log/sandstorm/log`) to see that it fetched the certificates without problems
- Double check that the files are on `[sandstorm_dir]/data/var/sandcats/https/yourname.sandcats.io` (they are like timestamps with `.csr` or `response-json` extensions or no extension, with the timestamp being the expiration date)
- Finally stop sandstorm, and if you run it dockerized unexport the 443 port but expose the HTTP port (see below in the network section) or if you are running it uncontained change or disable the `HTTPS_PORT` setting as needed.
- Wake up both your reverse proxy and sandstorm services.

#### Run the script on this repo

This will get Sandcats.io certs in your reverse proxy directory (for nginx this would tipically be `/etc/nginx/ssl`). Since Sancats.io certificates must be renewed weekly I suggest to add this to your cron. An example call could be:

```bash
python get_sandcats_certs.py --certs_origin_dir='/opt/sandstorm/var/sandcats/https/myname.sandcats.io' \
                             --certs_dest_dir='/etc/nginx/conf/ssl' \
                             --key_filename='sandstorm.key' \
                             --cert_filename='sandstorm.pem'
```

Please note that the `key_filename` and `cert_filename` parameters are the desired filenames on the **DESTINATION** path (the ones that your reverse proxy will use), not the original ones on the Sandstorm directory; for those the script will take care of finding the most recent ones an extracting them from the JSON files they're stored in.

#### Configure Sandstorm network parameters

Configure Sandstorm to serve **unencripted HTTP** on any port that is not 443 and not accesible from the Internet (for example, leaving the default 6080 port). If you are [running Sandstorm on a Docker container](https://docs.sandstorm.io/en/latest/install/#option-6-using-sandstorm-within-docker) (like I do) just remove the `-p` parameter for the `docker run` command and add the port as a `--expose` like:

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

*(but don't do this on containers - remember that every container with Docker has its own IP so if you do this it won't allow connections from your reverse proxy).*

### Configure the reverse proxy

The reverse proxy will receive the HTTPS connections securely at the `https://yourname.sandcats.io` domain on the normal 443 port, using Sandstorm certificates and will proxy them to your Sandstorm service.

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
Dont forget to point the `ssl_certificate` and `ssl_certificate_key` options to the directory where the script copied the certificates. Then restart the reverse proxy checking the logs so see if there is any problem with your config and restart sandstorm. The service should be accesible using your normal `https://yourname.sandcats.io` domain.
