#!/usr/bin/env python3
"""Lambda energy manager connector

Read data from an energy manager and send it to a lambda heatpump
in order to increase self-consumption.

usage:

python3 lambda-modbus-tcp.py [-h] [--source-type {se}] --source-host SOURCE_HOST [--source-port SOURCE_PORT] [--source-unit SOURCE_UNIT] --dest-host
                            DEST_HOST [--dest-port DEST_PORT] [--dest-type {negative,positive}] [-d] [-i INTERVAL]
                            [--log {critical,error,warning,info,debug}]

Connect energy manager and lambda heatpump

optional arguments:
  -h, --help            show this help message and exit
  --source-type {se}    "se": Solaredge
  --source-host SOURCE_HOST
                        source host address
  --source-port SOURCE_PORT
                        source port
  --source-unit SOURCE_UNIT
                        source unit
  --dest-host DEST_HOST
                        heat pump host address
  --dest-port DEST_PORT
                        heat pump port to use
  --dest-type {negative,positive}
                        "negative": send excess as negative value, "positive": send excess as is
  -d, --daemon          run in daemon mode (ignores exceptions)
  -i INTERVAL, --interval INTERVAL
                        interval in seconds for reading/writing
  --log {critical,error,warning,info,debug}
                        "critical", "error", "warning", "info" or "debug"

"""

import argparse
import logging
import time
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
import math

# setup logging
FORMAT = "%(asctime)-15s %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s"
logging.basicConfig(format=FORMAT)
_logger = logging.getLogger()


def read_registers(response, count, what):
    """Return the registers of a modbus response, raise if the response is an error or incomplete"""
    if response.isError():
        raise RuntimeError("Failed to read {}: {}".format(what, response))
    registers = getattr(response, "registers", None)
    if registers is None or len(registers) < count:
        raise RuntimeError("Incomplete response reading {}: {}".format(what, response))
    return registers


# Meter implementations
class Meter:
    def read(self):
        raise NotImplementedError


class Fronius(Meter):

    def __init__(self, host, port, unit):
        _logger.info("Connecting to Fronius SmartMeter {}:{}:{}".format(host, port, unit))
        self.smartMeter = ModbusTcpClient(host, port=port)
        self.unit = unit
        self.reconnect()

    def reconnect(self):
        self.smartMeter.close()
        self.smartMeter.connect()

    def read(self):
        power = read_registers(self.smartMeter.read_holding_registers(40087, 1, self.unit), 1, "smart meter power")
        decodedPower = BinaryPayloadDecoder.fromRegisters(power,byteorder=Endian.BIG, wordorder=Endian.BIG).decode_16bit_int()

        factor = read_registers(self.smartMeter.read_holding_registers(40091, 1, self.unit), 1, "smart meter scale factor")
        decodedScale = BinaryPayloadDecoder.fromRegisters(factor,byteorder=Endian.BIG, wordorder=Endian.BIG).decode_16bit_int()

        scaledPower = decodedPower * math.pow(10, decodedScale) * -1
        _logger.debug("decodedPower: {}, decodedScale: {}, scaledPower: {}".format(decodedPower, decodedScale, scaledPower))

        return int(scaledPower)


class SolarEdge(Meter):

    def __init__(self, host, port, unit):
        import solaredge_modbus

        self.meters = None
        _logger.info("Connecting to SE inverter {}:{}:{}".format(host, port, unit))
        self.inverter = solaredge_modbus.Inverter(host=host, port=port, unit=unit)
        self.reconnect()

    def read(self):
        if self.inverter.connected() is False:
            self.reconnect()
        value = 0
        for k in self.meters.keys():
            value += self.meters[k].read_all()['power']
        return value

    def reconnect(self):
        self.inverter.connect()
        if not self.inverter.connected():
            raise RuntimeError("Failed to connect to solar edge inverter")
        self.meters = self.inverter.meters()


class StaticValue(Meter):

    def __init__(self, value):
        self.value = value

    def read(self):
        return self.value

    def reconnect(self):
        pass


def create_meter(t, host, port, unit, value):
    if t == "se":
        return SolarEdge(host, port, unit)
    elif t == "fsm":
        return Fronius(host, port, unit)
    elif t == "static":
        return StaticValue(value)
    raise KeyError("unknown meter type")


# heatpump connectors
class HeatPump:
    def write(self, value):
        raise NotImplementedError


class Lambda(HeatPump):
    POWER_REGISTER = 102

    @staticmethod
    def __negative_transform(v):
        if v <= 0:
            return min(-v, 0x7fff)
        elif v < 0x8000:
            return 0x10000 - v
        return 0x8000

    @staticmethod
    def __positive_transform(v):
        return v

    def __init__(self, host, port, value_transform):
        _logger.info("Connecting to Lambda heat pump {}:{}".format(host, port))
        self.heat_pump = ModbusTcpClient(host, port=port)
        self.reconnect()
        if value_transform == "negative":
            self.transform = self.__negative_transform
        elif value_transform == "positive":
            self.transform = self.__positive_transform
        else:
            raise KeyError("unknown value transform")

    # expects excess as a positive value. Depending on --dest-type, the excess might be transformed to negative value
    def write(self, value):
        self.check()
        valueTransformed = self.transform(value)
        _logger.debug("val after transform {}".format(valueTransformed))
        r = self.heat_pump.write_registers(102, valueTransformed)
        if r.isError():
            raise RuntimeError("Error writing value: {}".format(r))
        _logger.debug("Wrote value {} (hex: {}) to lambda heat pump".format(value, hex(valueTransformed)))

    def check(self):
        r = self.heat_pump.read_holding_registers(1)
        if r.isError():
            self.reconnect()
            r = self.heat_pump.read_holding_registers(1)
        state = read_registers(r, 1, "heat pump state")[0]
        if state == 0:
            raise RuntimeError("Lambda heatpump is turned off")
        if state == 3:
            raise RuntimeError("Lambda heatpump reports error")

    def reconnect(self):
        self.heat_pump.close()
        self.heat_pump.connect()


def create_dest(t, host, port, value_transform):
    if t == "lambda":
        return Lambda(host, port, value_transform)
    raise KeyError("unknown heat pump type")


# Daemon

def loop(source, dest, interval, daemon):
    while True:
        try:
            if dest:
                dest.write(source.read())
            time.sleep(interval)
        except Exception as e:
            if not daemon:
                raise e
            else:
                # full traceback only on debug level, these errors are expected while a device is unreachable
                _logger.error("Failed to read/write energy value, automatically retrying: {}".format(e),
                              exc_info=e if _logger.isEnabledFor(logging.DEBUG) else None)
                time.sleep(interval)
                try:
                    source.reconnect()
                    if dest:
                        dest.reconnect()
                except Exception as reconnect_error:
                    _logger.error("Failed to reconnect, automatically retrying: {}".format(reconnect_error))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Connect energy manager and lambda heatpump"
    )
    parser.add_argument(
        "--source-type",
        choices=["se", "fsm", "static"],
        help='"se": Solaredge, "fsm": ForniusSmartMeter, "static": Simulate a static value',
        type=str,
        default="se"
    )

    parser.add_argument(
        "--source-host",
        help='source host address',
        type=str,
        required=False
    )

    parser.add_argument(
        "--source-port",
        help='source port',
        type=int,
        default=502
    )

    parser.add_argument(
        "--source-unit",
        help='source unit',
        type=int,
        default=1
    )

    parser.add_argument(
        "--source-value",
        help='source value',
        type=int,
        default=2000
    )

    parser.add_argument(
        "--dest-host",
        help='heat pump host address',
        type=str,
        required=True
    )

    parser.add_argument(
        "--dest-port",
        help="heat pump port to use",
        type=int,
        default=502
    )

    parser.add_argument(
        "--dest-type",
        choices=["negative", "positive"],
        help='"negative": send excess as negative value, "positive": send excess as is',
        type=str,
        default="negative"
    )

    parser.add_argument(
        "-d",
        "--daemon",
        action='store_true',
        help='run in daemon mode (ignores exceptions)'
    )

    parser.add_argument(
        "-i",
        "--interval",
        help='interval in seconds for reading/writing',
        type=float,
        default=1.0
    )

    parser.add_argument(
        "--log",
        choices=["critical", "error", "warning", "info", "debug"],
        help='"critical", "error", "warning", "info" or "debug"',
        type=str,
    )

    args = parser.parse_args()

    _logger.setLevel(args.log.upper() if args.log else logging.INFO)

    source = create_meter(args.source_type, args.source_host, args.source_port, args.source_unit, args.source_value)
    dest = create_dest("lambda", args.dest_host, args.dest_port, args.dest_type)
    loop(source, dest, args.interval, args.daemon)
