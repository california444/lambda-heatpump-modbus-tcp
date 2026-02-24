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

```
python3 lambda-modbus-tcp.py --source-host 192.168.0.106 --dest-host 192.168.0.188 --source-port 1502 --source-unit=4
```

Example usage for Fronius Smart Meter:

```
python3 lambda-modbus-tcp.py --source-type fsm --source-host 192.168.0.106 --dest-host 192.168.0.188 --source-port 502 --dest-port 502 --source-unit 200 -d -i 15
```

Demo mode:

Using the "static meter" you can simulate a given value. E.g. to write 1500W use:

```
python3 lambda-modbus-tcp.py --source-type static --dest-host 192.168.0.188 -d -i 5 --source-value 1500
```

## Docker Compose

A simple `docker-compose.yml` example to run the container with environment variables (override values as needed):

```yaml
version: "3.9"

services:
	heatpump:
		image: california444/lambda-heatpump-modbus-tcp:latest
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
