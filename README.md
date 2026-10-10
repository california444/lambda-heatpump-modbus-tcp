# lambda-heatpump-modbus-tcp

(PV Überschuss Steuerung für Lambda Wärmepumpen)

Simple script to connect energy meter with a lambda heatpump over modbus tcp to prioritize execution at times of excess photovoltaic production:

Supports:

- Solaredge energy meter (using [solaredge modbus](https://pypi.org/project/solaredge-modbus/))
- Fronius Smart Meter
- Lambda heatpump EU08L, EU13L

Installation:

- install pymodbus (pip3 install pymodbus)
- install solaredge_modbus (pip3 install solaredge_modbus) if a Solaredge energy meter is used

Example usage:

```bash
python3 lambda-modbus-tcp.py --source-host 192.168.0.106 --dest-host 192.168.0.188 --source-port 1502 --source-unit=4
```

Example usage for Fronius Smart Meter:

```bash
python3 lambda-modbus-tcp.py --source-type fsm --source-host 192.168.0.106 --dest-host 192.168.0.188 --source-port 502 --dest-port 502 --source-unit 200 -d -i 15
```

Demo mode:

Using the "static meter" you can simulate a given value. E.g. to write 1500W use:

```bash
python3 lambda-modbus-tcp.py --source-type static --dest-host 192.168.0.188 -d -i 5 --source-value 1500
```

Tests:

```bash
python3 -m unittest discover -s tests -v
```

## Docker Compose

The image is built and published to the GitHub Container Registry on every push to `main` and once a week (to pick up base image updates), for `linux/arm64` (Raspberry Pi):

- `ghcr.io/california444/lambda-heatpump-modbus-tcp:latest`: current state of `main`
- `ghcr.io/california444/lambda-heatpump-modbus-tcp:sha-<commit>`: fixed build of a single commit, e.g. for a rollback
- `ghcr.io/california444/lambda-heatpump-modbus-tcp:<YYYYMMDD>`: build of a given day

The container is configured with environment variables. Only `DEST_HOST` is required (and `SOURCE_HOST` unless `SOURCE_TYPE` is `static`), all others fall back to their default. The same variables also work without Docker, command line arguments take precedence.

| Variable | Argument | Default | Description |
| --- | --- | --- | --- |
| `SOURCE_TYPE` | `--source-type` | `se` | `se`: Solaredge, `fsm`: Fronius Smart Meter, `static`: simulate a static value |
| `SOURCE_HOST` | `--source-host` | | energy meter host address |
| `SOURCE_PORT` | `--source-port` | `502` | energy meter port |
| `SOURCE_UNIT` | `--source-unit` | `1` | energy meter modbus unit |
| `SOURCE_VALUE` | `--source-value` | `2000` | value in W for the static meter |
| `DEST_HOST` | `--dest-host` | | heat pump host address |
| `DEST_PORT` | `--dest-port` | `502` | heat pump port |
| `DEST_TYPE` | `--dest-type` | `negative` | `negative`: send excess as negative value, `positive`: send excess as is |
| `INTERVAL` | `--interval` | `1` | interval in seconds for reading/writing |
| `LOG_LEVEL` | `--log` | `info` | `critical`, `error`, `warning`, `info` or `debug` |

The container runs in daemon mode (`-d`), which keeps running after errors.

The [docker-compose.yml](docker-compose.yml) in this repository is an example to run the container with environment variables (override values as needed):

```yaml
version: "3.9"

services:
 heatpump:
  image: ghcr.io/california444/lambda-heatpump-modbus-tcp:latest
  container_name: lambda-heatpump-modbus-tcp
  restart: unless-stopped
  environment:
   TZ: "Europe/Berlin"
   SOURCE_TYPE: "fsm"
   SOURCE_HOST: "192.168.0.25"
   DEST_HOST: "192.168.0.106"
   SOURCE_PORT: "502"
   DEST_PORT: "502"
   SOURCE_UNIT: "200"
   INTERVAL: "9"
   LOG_LEVEL: "debug"
  logging:
   driver: "json-file"
   options:
    max-size: "10m"
    max-file: "1"
```
