#!/usr/bin/env python3
"""Tests for the Fronius meter and the Lambda heat pump connector

usage:

python3 -m unittest discover -s tests -v
"""

import importlib.util
import os
import unittest
from unittest import mock

from pymodbus.exceptions import ConnectionException, ModbusIOException
from pymodbus.pdu import ExceptionResponse
from pymodbus.register_read_message import ReadHoldingRegistersResponse
from pymodbus.register_write_message import WriteMultipleRegistersResponse

# the script name contains hyphens, so it cannot be imported with a regular import statement
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lambda-modbus-tcp.py")
spec = importlib.util.spec_from_file_location("lambda_modbus_tcp", SCRIPT)
lmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lmt)


def registers(*values):
    return ReadHoldingRegistersResponse(list(values))


def responses(*values):
    """side_effect returning the given responses one after another

    pymodbus returns IO errors instead of raising them, a plain side_effect list would raise them
    """
    iterator = iter(values)
    return lambda *args, **kwargs: next(iterator)


class ModbusTestCase(unittest.TestCase):
    """Replaces the modbus client with a mock, so no device is needed"""

    def setUp(self):
        patcher = mock.patch.object(lmt, "ModbusTcpClient")
        self.client_class = patcher.start()
        self.client = self.client_class.return_value
        self.addCleanup(patcher.stop)


class FroniusTest(ModbusTestCase):

    def create(self):
        return lmt.Fronius("192.168.0.25", 502, 200)

    def test_connects_on_creation(self):
        self.create()
        self.client_class.assert_called_once_with("192.168.0.25", port=502)
        self.client.connect.assert_called_once_with()

    def test_reads_power_and_scale_factor_registers(self):
        self.client.read_holding_registers.side_effect = responses(registers(1500), registers(0))
        self.create().read()
        self.assertEqual(
            self.client.read_holding_registers.call_args_list,
            [mock.call(40087, 1, 200), mock.call(40091, 1, 200)]
        )

    def test_grid_consumption_is_returned_as_negative_excess(self):
        self.client.read_holding_registers.side_effect = responses(registers(1500), registers(0))
        self.assertEqual(self.create().read(), -1500)

    def test_grid_feed_in_is_returned_as_positive_excess(self):
        # -1500 as 16 bit two's complement
        self.client.read_holding_registers.side_effect = responses(registers(0x10000 - 1500), registers(0))
        self.assertEqual(self.create().read(), 1500)

    def test_negative_scale_factor(self):
        # scale factor -1 as 16 bit two's complement
        self.client.read_holding_registers.side_effect = responses(registers(0x10000 - 12345), registers(0xffff))
        self.assertEqual(self.create().read(), 1234)

    def test_positive_scale_factor(self):
        self.client.read_holding_registers.side_effect = responses(registers(0x10000 - 15), registers(2))
        self.assertEqual(self.create().read(), 1500)

    def test_zero_power(self):
        self.client.read_holding_registers.side_effect = responses(registers(0), registers(0))
        self.assertEqual(self.create().read(), 0)

    def test_io_error_on_power_raises(self):
        self.client.read_holding_registers.side_effect = responses(ModbusIOException("no response"), registers(0))
        with self.assertRaisesRegex(RuntimeError, "smart meter power"):
            self.create().read()

    def test_io_error_on_scale_factor_raises(self):
        self.client.read_holding_registers.side_effect = responses(registers(1500), ModbusIOException("no response"))
        with self.assertRaisesRegex(RuntimeError, "smart meter scale factor"):
            self.create().read()

    def test_exception_response_raises(self):
        self.client.read_holding_registers.side_effect = responses(ExceptionResponse(3, 2), registers(0))
        with self.assertRaisesRegex(RuntimeError, "smart meter power"):
            self.create().read()

    def test_empty_response_raises(self):
        # seen while the smart meter was starting up, used to fail with struct.error
        self.client.read_holding_registers.side_effect = responses(registers(), registers(0))
        with self.assertRaisesRegex(RuntimeError, "Incomplete response"):
            self.create().read()

    def test_connection_error_is_passed_on(self):
        self.client.read_holding_registers.side_effect = ConnectionException("Failed to connect")
        with self.assertRaises(ConnectionException):
            self.create().read()

    def test_reconnect_opens_a_new_connection(self):
        meter = self.create()
        self.client.reset_mock()
        meter.reconnect()
        self.assertEqual(self.client.mock_calls, [mock.call.close(), mock.call.connect()])


class LambdaTest(ModbusTestCase):
    STATE_OFF = 0
    STATE_RUNNING = 1
    STATE_ERROR = 3

    def setUp(self):
        super().setUp()
        self.client.read_holding_registers.return_value = registers(self.STATE_RUNNING)
        self.client.write_registers.return_value = WriteMultipleRegistersResponse(102, 1)

    def create(self, value_transform="negative"):
        return lmt.Lambda("192.168.0.106", 502, value_transform)

    def written(self, value, value_transform="negative"):
        self.create(value_transform).write(value)
        self.client.write_registers.assert_called_once()
        address, written_value = self.client.write_registers.call_args[0]
        self.assertEqual(address, lmt.Lambda.POWER_REGISTER)
        return written_value

    def test_connects_on_creation(self):
        self.create()
        self.client_class.assert_called_once_with("192.168.0.106", port=502)
        self.client.connect.assert_called_once_with()

    def test_unknown_value_transform_raises(self):
        with self.assertRaises(KeyError):
            self.create("unknown")

    def test_negative_transform_sends_excess_as_negative_value(self):
        # -1500 as 16 bit two's complement
        self.assertEqual(self.written(1500), 0x10000 - 1500)

    def test_negative_transform_sends_consumption_as_positive_value(self):
        self.assertEqual(self.written(-1500), 1500)

    def test_negative_transform_zero(self):
        self.assertEqual(self.written(0), 0)

    def test_negative_transform_limits_excess_to_16_bit(self):
        self.assertEqual(self.written(0x7fff), 0x8001)
        self.assertEqual(self.written_again(0x8000), 0x8000)
        self.assertEqual(self.written_again(50000), 0x8000)

    def test_negative_transform_limits_consumption_to_16_bit(self):
        self.assertEqual(self.written(-0x7fff), 0x7fff)
        self.assertEqual(self.written_again(-50000), 0x7fff)

    def test_positive_transform_sends_value_as_is(self):
        self.assertEqual(self.written(1500, "positive"), 1500)

    def test_state_is_checked_before_writing(self):
        self.create().write(1500)
        self.client.read_holding_registers.assert_called_once_with(1)

    def test_heat_pump_turned_off_raises_and_does_not_write(self):
        self.client.read_holding_registers.return_value = registers(self.STATE_OFF)
        with self.assertRaisesRegex(RuntimeError, "turned off"):
            self.create().write(1500)
        self.client.write_registers.assert_not_called()

    def test_heat_pump_error_raises_and_does_not_write(self):
        self.client.read_holding_registers.return_value = registers(self.STATE_ERROR)
        with self.assertRaisesRegex(RuntimeError, "reports error"):
            self.create().write(1500)
        self.client.write_registers.assert_not_called()

    def test_failed_state_read_reconnects_and_retries(self):
        self.client.read_holding_registers.side_effect = responses(
            ModbusIOException("no response"), registers(self.STATE_RUNNING)
        )
        heat_pump = self.create()
        self.client.close.reset_mock()
        self.client.connect.reset_mock()
        heat_pump.write(1500)
        self.client.close.assert_called_once_with()
        self.client.connect.assert_called_once_with()
        self.client.write_registers.assert_called_once()

    def test_state_read_failing_twice_raises_and_does_not_write(self):
        # used to fail with AttributeError: 'ModbusIOException' object has no attribute 'registers'
        self.client.read_holding_registers.return_value = ModbusIOException("no response")
        with self.assertRaisesRegex(RuntimeError, "heat pump state"):
            self.create().write(1500)
        self.assertEqual(self.client.read_holding_registers.call_count, 2)
        self.client.write_registers.assert_not_called()

    def test_empty_state_response_raises(self):
        self.client.read_holding_registers.return_value = registers()
        with self.assertRaisesRegex(RuntimeError, "Incomplete response"):
            self.create().write(1500)

    def test_io_error_on_write_raises(self):
        self.client.write_registers.return_value = ModbusIOException("no response")
        with self.assertRaisesRegex(RuntimeError, "Error writing value"):
            self.create().write(1500)

    def test_exception_response_on_write_raises(self):
        self.client.write_registers.return_value = ExceptionResponse(16, 2)
        with self.assertRaisesRegex(RuntimeError, "Error writing value"):
            self.create().write(1500)

    def test_connection_error_is_passed_on(self):
        self.client.read_holding_registers.side_effect = ConnectionException("Failed to connect")
        with self.assertRaises(ConnectionException):
            self.create().write(1500)

    def test_reconnect_opens_a_new_connection(self):
        heat_pump = self.create()
        self.client.reset_mock()
        heat_pump.reconnect()
        self.assertEqual(self.client.mock_calls, [mock.call.close(), mock.call.connect()])

    def written_again(self, value, value_transform="negative"):
        self.client.write_registers.reset_mock()
        return self.written(value, value_transform)


if __name__ == "__main__":
    unittest.main()
