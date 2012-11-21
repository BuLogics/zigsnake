from telnetlib import Telnet
import unittest
import zcl
import inspect
import time
import sys

def write_log(level, log_string):
    pass
    #print log_string

class Validator:
    '''
    This class is used as a superclass to collect validators that can be used
    in expect_command calls. Subclasses should implement a 'validate' function
    that will take in the received value and return True or False.
    '''
    pass

class Equal(Validator):
    '''
    Validates that the received value is equal to the expected.
    '''
    def __init__(self, expected):
        self.expected = expected
    def validate(self, received):
        if self.expected != received:
            raise AssertionError("Expected %s, Received %s" %
                    (str(self.expected), str(received)))

class Between(Validator):
    '''
    Validates that the received is between the low and high limits given
    (inclusive).
    '''
    def __init__(self, low, high):
        self.low = low
        self.high = high
    def validate(self, received):
        if received < self.low or received > self.high:
            raise AssertionError("Received %d, not between %d and %d" % (received, self.low, self.high))

class ZBController:
    def __init__(self):
        self.conn = Telnet()
        self.sequence = 0

    def open(self, hostname):
        Telnet.open(self.conn, hostname, 4900)

    def _network_command(self, command, args, status_prefix):
        self.write('network %s %s' % (command, args))
        _, match, _ = self.conn.expect(['%s (0x[0-9A-F]{2})' % status_prefix], timeout=2)
        if match is None:
            raise TimeoutError()
        return int(match.group(1), 0)

    def form_network(self, channel=19, power=0, pan_id = 0xfafa):
        status = self._network_command('form', '%d %d 0x%04x' %
                (channel, power, pan_id), 'form')
        if status == 0x70:
            #already in network
            pass
        elif status != 0x00:
            raise UnhandledStatusError()

    def leave_network(self):
        status = self._network_command('leave', '', 'leave')
        if status == 0x70:
            # already out of network
            pass
        elif status == 0x00:
            out = self.conn.read_until('EMBER_NETWORK_DOWN', timeout=2)
            if not out.endswith('EMBER_NETWORK_DOWN'):
                raise TimeoutError()
        else:
            raise UnhandledStatusError()

    def enable_permit_join(self):
        status = self._network_command('pjoin', '0xff', 'pJoin for 255 sec:')
        if status != 0x00:
            raise NetworkOperationError("Error enabling pjoin: 0x%x" % status)

    def disable_permit_join(self):
        status = self._network_command('pjoin', '0x00', 'pJoin for 0 sec:')
        if status == 0x00:
            print "Pjoin Disabled"
        else:
            print "Error disabling pjoin: 0x%x" % status

    def wait_for_join(self):
        _, match, _ = self.conn.expect(['Device Announce: (0x[0-9A-F]{4})'])
        if match is None:
            raise TimeoutError()
        print 'Device %s joined' % match.group(1)
        return int(match.group(1), 0)

    def send_zcl_command(self, destination, cmd):
        payload = []
        for arg in cmd.args:
            payload += _list_from_arg(arg.type, arg.value)
        self.write('raw 0x%04X {01 %02X %02X %s}' %
                (cmd.cluster_code, self.sequence, cmd.code,
                " ".join(["%02X" % x for x in payload])))
        self.write('send 0x%04X 1 1' % destination)
        self.sequence = self.sequence + 1 % 0x100
        #TODO: wait for response

    def send_zcl_ota_notify(self, destination, cmd):
        payload = []
        for arg in cmd.args:
            payload += _list_from_arg(arg.type, arg.value)
        self.write('zcl ota server notify 0x%04X %02X %s' %
                (destination, 1, " ".join(["0x%04X" % x for x in payload])))
        self.sequence = self.sequence + 1 % 0x100

    def bind_node(self, node_id, node_ieee_address, cluster_id):
        '''
        Binds a destination node to us.
        Expects node_id and cluster_id as integers, and node_ieee_address as
        a string with hex bytes separated by spaces.
        '''
        self.write('zdo bind %d 1 1 %d {%s} {}' % (
                node_id, cluster_id, node_ieee_address))
        #TODO: wait for response

    def write_attribute(self, destination, attribute, value):
        '''
        Writes an attribute on a device. Attributes are instances of
        ZCLAttribute.
        '''

        payload = _list_from_arg(attribute.type, value)
        write_log(0, "Writing Attribute %s to %s" % (attribute.name,
                " ".join(['%02X' % x for x in payload])))
        self.write('zcl global write %d %d %d {%s}' %
                (attribute.cluster_code, attribute.code, attribute.type_code,
                " ".join(['%02X' % x for x in payload])))
        self.write('send 0x%04X 1 1' % destination)
        #TODO: wait for response

    def write_local_attribute(self, attribute, value):
        '''
        Writes an attribute that's local to the controller.
        '''
        payload = _list_from_arg(attribute.type, value)
        payload_string = " ".join(['%02X' % x for x in payload])
        self.write('write 1 %d %d 1 %d {%s}' % (
            attribute.cluster_code, attribute.code, attribute.type_code,
            payload_string))
        time.sleep(1)

    def make_server(self):
        self.write('zcl global direction 1')

    def make_client(self):
        self.write('zcl global direction 0')

#T000BD5C5:RX len 11, ep 01, clus 0x000A (Time) FC 18 seq 20 cmd 01 payload[00 00 00 E2 00 00 00 00 ]
#READ_ATTR_RESP: (Time)
#- attr:0000, status:00
#type:E2, val:00000000
    def read_attribute(self, destination, attribute, timeout=10):
        self.write('zcl global read %d %d' %
                (attribute.cluster_code, attribute.code))
        self.write('send 0x%04X 1 1' % destination)
        _, match, _ = self.conn.expect(['RX len [0-9]+, ep [0-9A-Z]+, ' +
            'clus 0x%04X \([a-zA-Z0-9\.\[\]\(\) ]+\) .* cmd 01 payload\[([0-9A-Z ]*)\]' % attribute.cluster_code],
            timeout=timeout)
        if match is None:
            raise AssertionError('TIMED OUT reading attribute %s' % attribute.name)
        payload = [int(x, 16) for x in match.group(1).split()]
        attribute_id = _pop_argument('INT16U', payload)
        status = _pop_argument('INT8U', payload)
        if status != 0:
            raise AssertionError('Attribute Read failed with status 0x%02X' % status)
        attribute_type_code = _pop_argument('INT8U', payload)
        attribute_type = zcl.get_type_string(attribute_type_code)
        return _pop_argument(attribute_type, payload)

    def expect_zcl_command(self, command, timeout=10):
        '''
        Waits for an incomming message and validates it against the given
        cluster ID, command ID, and arguments. Any arguments given as None
        are ignored. Returns True for success or False for failure.
        '''
        # read and discard any data already queued up in the buffer
        self.conn.read_eager()
        _, match, _ = self.conn.expect(['RX len [0-9]+, ep [0-9A-Z]+, ' +
            'clus 0x%04X \([a-zA-Z ]+\) .* cmd %02X payload\[([0-9A-Z ]*)\]'
            % (command.cluster_code, command.code)], timeout=timeout)
        if match is None:
            raise AssertionError("TIMED OUT waiting for " + command.name)
        payload = [int(x, 16) for x in match.group(1).split()]
        _validate_payload(command.args, payload)

    def write(self, msg):
        self.conn.write(msg + '\n')

class TimeoutError(StandardError):
    pass

class UnhandledStatusError(StandardError):
    pass

class NetworkOperationError(StandardError):
    pass

def _list_from_arg(type, value):
    '''
    Takes in a type string and a value and returns the value converted
    into a list suitable for a ZCL payload.
    >>> _list_from_arg('INT8U', 0x30)
    [48]
    >>> _list_from_arg('CHAR_STRING', '6789')
    [4, 54, 55, 56, 57]
    >>> _list_from_arg('OCTET_STRING', [6, 7, 8, 9])
    [4, 6, 7, 8, 9]
    '''
    if type in ['ENUM8', 'INT8U']:
        if value < 0 or value > 0xff:
            raise ValueError
        return [value]
    if type == 'INT8S':
        if value < -128 or value > 127:
            raise ValueError
        return [value]
    if type in ['INT16U', 'ENUM16', 'BITMAP16']:
        if value < 0 or value > 0xffff:
            raise ValueError
        return [value & 0xff, value >> 8]
    if type in ['INT32U', 'UTC_TIME', 'IEEE_ADDRESS', 'BITMAP32']:
        if value < 0 or value > 0xffffffff:
            raise ValueError
        return [value & 0xff,
                (value >> 8) & 0xff,
                (value >> 16) & 0xff,
                value >> 24]
    if type == 'INT32S':
        #TODO: add min/max value checking
        if value < 0:
            value = ~(abs(value) - 1)
        return [value & 0xff,
                (value >> 8) & 0xff,
                (value >> 16) & 0xff,
                (value >> 24) & 0xff]

    if type == 'CHAR_STRING':
        # expects a string as a value
        payload = [len(value)]
        for char in value:
            payload.append(ord(char))
        return payload
    if type == 'OCTET_STRING':
        # expects a list of bytes as a value
        payload = [len(value)]
        for byte in value:
            payload += _list_from_arg('INT8U', byte)
        return payload
    print "WARNING: unrecognized type %s. Assuming INT8U" % type
    return _list_from_arg('INT8U', value)

def _validate_payload(arglist, payload):
    '''
    Takes a list of ZCLCommandArgs and compares a received payload
    against the expected values

    >>> arglist = [ZCLCommandArg('arg1', 'INT8U', 10),
    ...        ZCLCommandArg('arg2', 'INT16U', 32),
    ...        ZCLCommandArg('arg3', 'INT8U', None)]
    >>> _validate_payload(arglist, [0x0A, 0x20, 0x00, 0x30])
    True
    >>> _validate_payload(arglist, [0x0B, 0x20, 0x00, 0x42])
    Wrong value for arg1: Expected 10, got 11
    False
    '''
    try:
        for arg in arglist:
            received = _pop_argument(arg.type, payload)
            if arg.value is None:
                # don't validate if expected value is None
                continue
            elif Validator in inspect.getmro(arg.value.__class__):
                #TODO: don't break demeter without good reason
                arg.value.validate(received)
            else:
                # arg value isn't a validator, fall back to simple comparison
                Equal(arg.value).validate(received)
    except AssertionError as e:
        # catch and re-throw, adding the argument name to the error message
        raise AssertionError("Wrong value for %s: %s" % (arg.name, str(e)))

def _pop_argument(type, payload):
    '''
    Takes a type string and a paylaod (list of 1-byte values) and
    pops off the correct number of bytes from the front of the payload,
    formatting the result and returning it.

    >>> test_list = [1, 0x92, 0x10, 4, 3, 2, 1, 3, 0x32, 0x33, 0x34,
    ...        3, 42, 43, 44]
    >>> _pop_argument('INT8U', test_list)
    1
    >>> _pop_argument('INT16U', test_list)
    4242
    >>> _pop_argument('INT32U', test_list)
    16909060
    >>> _pop_argument('CHAR_STRING', test_list)
    '234'
    >>> _pop_argument('OCTET_STRING', test_list)
    [42, 43, 44]
    '''
    if type in ['ENUM8', 'INT8U', 'INT8S']:
        return payload.pop(0)
    if type in ['INT16U', 'ENUM16', 'BITMAP16']:
        lsb = payload.pop(0)
        msb = payload.pop(0)
        return (msb << 8) | lsb
    if type in ['INT32U', 'UTC_TIME', 'IEEE_ADDRESS', 'BITMAP32']:
        byte0 = payload.pop(0)
        byte1 = payload.pop(0)
        byte2 = payload.pop(0)
        byte3 = payload.pop(0)
        return (byte3 << 24) | (byte2 << 16) | (byte1 << 8) | byte0
    if type == 'INT32S':
        byte0 = payload.pop(0)
        byte1 = payload.pop(0)
        byte2 = payload.pop(0)
        byte3 = payload.pop(0)
        value = (byte3 << 24) | (byte2 << 16) | (byte1 << 8) | byte0
        if value & 0x80000000:
            return -((~value + 1) & 0xFFFFFFFF)
        else:
            return value
    if type == 'CHAR_STRING':
        string = ''
        string_len = payload.pop(0)
        while(string_len):
            string += chr(payload.pop(0))
            string_len -= 1
        return string
    if type == 'OCTET_STRING':
        string = []
        string_len = payload.pop(0)
        while(string_len):
            string.append(payload.pop(0))
            string_len -= 1
        return string
    print "WARNING: unrecognized type %s. Assuming INT8U" % type
    return _pop_argument('INT8U', payload)

if __name__ == '__main__':
    import doctest
    doctest.testmod()

