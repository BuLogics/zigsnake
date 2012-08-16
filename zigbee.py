from telnetlib import Telnet
import xml.etree.ElementTree as xml

class ZCLCluster:
    def __init__(self, cluster_xml):
        self.name = cluster_xml.find('name').text
        self.define = cluster_xml.find('define').text
        self.code = int(cluster_xml.find('code').text, 0)
        self.add_commands(cluster_xml)
        self.add_attributes(cluster_xml)

    def add_commands(self, cluster_xml):
        for cmd_xml in cluster_xml.findall('command'):
            setattr(self,
                    _attr_from_name(cmd_xml.get('name')),
                    ZCLCommandPrototype(self.code, cmd_xml))

    def add_attributes(self, cluster_xml):
        for attr_xml in cluster_xml.findall('attribute'):
            setattr(self,
                    _attr_from_name(attr_xml.text),
                    ZCLAttribute(attr_xml))

class ZCLCommandCall:
    def __init__(self, proto, arglist):
        self.cluster_code = proto.cluster_code
        self.code = proto.code
        self.name = proto.name
        # copy the list to make sure there's no interaction with the given payload
        # note that we're not going as far as copying all the arguments.
        # maybe we should?
        self.args = list(arglist)

class ZCLCommandPrototype:
    '''
    ZCLCommandPrototype represents the call signiture of a ZCL Command.
    It is also callable, and when called will return a ZCLCommandCall object
    with the cluster ID, command ID, a list of the types and values
    '''
    def __init__(self, cluster_code, cmd_xml):
        # a ZCLCommandPrototype needs to know about its cluster ID so that it
        # can generate a proper ZCLCommandCall that can be passed to actually
        # send a message
        self.cluster_code = cluster_code
        self.name = cmd_xml.get('name')
        self.code = int(cmd_xml.get('code'), 0)
        # <pedantic>function parameters are mistakenly called
        # 'args' in the xml </pedantic>
        self.params = [ZCLCommandParam(xml) for xml in cmd_xml.findall('arg')]
    def __call__(self, *args):
        if len(args) != len(self.params):
            raise TypeError("%s() takes exactly %d arguments (%d given)\n" %
                    (_attr_from_name(self.name), len(self.params), len(args)) +
                    "\n".join(["\t\t%s (%s)" % (param.name, param.type) for
                        param in self.params]))
        arglist = [ZCLCommandArg(param.name, param.type, val) for param, val
                in zip(self.params, args)]
        return ZCLCommandCall(self, arglist)

class ZCLCommandParam:
    def __init__(self, param_xml):
        self.name = param_xml.get('name')
        self.type = param_xml.get('type')

class ZCLCommandArg:
    def __init__(self, name, type, value):
        self.name = name
        self.type = type
        self.value = value

class ZCLAttribute:
    def __init__(self, attr_xml=None):
        if attr_xml is None:
            return
        self.name = attr_xml.text
        self.code = int(attr_xml.get('code'), 0)
        self.type = attr_xml.get('type')
        self.type_code = zcl_attribute_types[self.type]
        if self.type in ['INT16U', 'INT16S', 'ENUM16', 'BITMAP16']:
            self.size = 2
        elif self.type in ['INT32U', 'INT32S', 'ENUM32', 'UTC_TIME', 'BITMAP32', 'IEEE_ADDRESS']:
            self.size = 4
        elif self.type in ['CHAR_STRING', 'OCTET_STRING']:
            self.size = None
        else:
            self.size = 1

class ZCLEnum():
    def __init__(self, enum_xml):
        self.name = enum_xml.get('name')
        for item_xml in enum_xml.findall('item'):
            setattr(self, _attr_from_name(item_xml.get('name')),
                int(item_xml.get('value'),0))

class ZCL():
    def __init__(self, xml_files = None):
        clusters = []
        if not xml_files:
            return
        for xml_file in xml_files:
            tree = xml.parse(xml_file)
            root = tree.getroot()
            for cluster_xml in root.iter('cluster'):
                setattr(self,
                        _attr_from_name(cluster_xml.find('name').text),
                        ZCLCluster(cluster_xml))
            for extension_xml in root.iter('clusterExtension'):
                for cluster in (getattr(self, match) for match in dir(self)):
                    if cluster.__class__ == ZCLCluster \
                            and cluster.code == int(extension_xml.get('code'), 0):
                        cluster.add_commands(extension_xml)
                        cluster.add_attributes(extension_xml)
            for enum_xml in root.iter('enum'):
                setattr(self,
                        _attr_from_name(enum_xml.get('name')),
                        ZCLEnum(enum_xml))

class ZBController():
    def __init__(self):
        self.conn = Telnet()
        self.sequence = 0

    def open(self, hostname):
        Telnet.open(self.conn, hostname, 4900)

    def _network_command(self, command, args, status_prefix):
        self.conn.write('network %s %s\n' % (command, args))
        _, match, _ = self.conn.expect(['%s (0x[0-9A-F]{2})' % status_prefix], timeout=2)
        if match is None:
            raise TimeoutError()
        return int(match.group(1), 0)

    def form_network(self):
        status = self._network_command('form', '19 0 0xbabe', 'form')
        if status == 0x70:
            print "Already in Network"
        elif status == 0x00:
            print "Successfully formed network"
        else:
            raise UnhandledStatusError()

    def leave_network(self):
        status = self._network_command('leave', '', 'leave')
        if status == 0x70:
            print "Already Out of Network"
        elif status == 0x00:
            out = self.conn.read_until('EMBER_NETWORK_DOWN', timeout=2)
            if out.endswith('EMBER_NETWORK_DOWN'):
                print "Successfully left network"
            else:
                raise TimeoutError()
        else:
            raise UnhandledStatusError()

    def enable_permit_join(self):
        status = self._network_command('pjoin', '0xff', 'pJoin for 255 sec:')
        if status == 0x00:
            print "Pjoin Enabled"
        else:
            print "Error enabling pjoin: 0x%x" % status

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
        self.conn.write('raw 0x%04X {01 %02X %02X %s}\n' %
                (cmd.cluster_code, self.sequence, cmd.code,
                " ".join(["%02X" % x for x in payload])))
        self.conn.write('send 0x%04X 1 1\n' % destination)
        self.sequence = self.sequence + 1 % 0x100

    def write_attribute(self, destination, attribute, value):
        '''
        Writes an attribute on a device. Attributes are instances of
        ZCLAttribute.
        '''

        payload = _list_from_arg(attribute.type, value)
        self.conn.write('zcl global write %d %d %d {%s}\n' %
                (attribute.cluster_code, attribute.code, attribute.type_code,
                " ".join(['%02X' % x for x in payload])))
        self.conn.write('send 0x%04X 1 1\n' % destination)

    def read_attribute(self, destination, attribute):
        self.conn.write('zcl global read %d %d\n' %
                (attribute.cluster_code, attribute.code))
        self.conn.write('send 0x%04X 1 1\n' % destination)
        self.conn.interact()
        _, match, _ = self.conn.expect([''])
        if match is None:
            print 'TIMED OUT reading attribute %s' % attribute.name
            return None
        #TODO: wait for response on cluster and attribute_id, and store
        # value

    #T000931A2:RX len 15, ep 01, clus 0x0101 (Door Lock) FC 09 seq 4E cmd 06 payload[06 00 01 00 06 06 36 37 38 39 30 30 ]
    def expect_command(self, command, timeout=10):
        '''
        Waits for an incomming message and validates it against the given
        cluster ID, command ID, and arguments. Any arguments given as None
        are ignored. Returns True for success or False for failure.
        '''
        # read and discard any data already queued up in the buffer
        self.conn.read_eager()
# T000AF5CA:RX len 4, ep 01, clus 0x0101 (Door Lock) FC 19 seq 13 cmd 01 payload[00 ]
        _, match, _ = self.conn.expect(['RX len [0-9]+, ep [0-9A-Z]+, ' +
            'clus 0x%04X \([a-zA-Z ]+\) .* cmd %02X payload\[([0-9A-Z ]*)\]'
            % (command.cluster_code, command.code)], timeout=timeout)
        if match is None:
            print "TIMED OUT waiting for " + command.name
            return False
        else:
            payload = [int(x, 16) for x in match.group(1).split()]
            return _validate_payload(command.args, payload)

class TimeoutError(StandardError):
    pass

class UnhandledStatusError(StandardError):
    pass

def _attr_from_name(name):
    '''
    This assumes that the name is either in CamelCase or
    words separated by spaces, and converts to all lowercase
    with words separated by underscores.

    >>> _attr_from_name('This is a name with spaces')
    'this_is_a_name_with_spaces'
    >>> _attr_from_name('this is a name with spaces')
    'this_is_a_name_with_spaces'
    >>> _attr_from_name('ThisIsACamelCaseName')
    'this_is_a_camel_case_name'
    >>> _attr_from_name('thisIsAnotherCamelCaseName')
    'this_is_another_camel_case_name'
    '''
    if ' ' in name:
        return name.replace(' ', '_').lower()
    #no spaces, so look for uppercase letters and prepend an underscore
    attr_name = ''
    for i, letter in enumerate(name):
        if letter.isupper() and i != 0:
            attr_name += '_'
        attr_name += letter.lower()
    return attr_name

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
    for arg in arglist:
        value = _pop_argument(arg.type, payload)
        if arg.value is not None and value != arg.value:
            print 'Wrong value for %s: Expected %s, got %s' % (arg.name,
                    str(arg.value), str(value))
            return False
    return True

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
    return _list_from_arg('INT8U', value)

# as far as I can tell this isn't stored in any of the XML
# files, so we just hard-code it here
zcl_attribute_types = {
    'NO_DATA'           : 0x00,
    'DATA8'             : 0x08,
    'DATA16'            : 0x09,
    'DATA24'            : 0x0A,
    'DATA32'            : 0x0B,
    'DATA40'            : 0x0C,
    'DATA48'            : 0x0D,
    'DATA56'            : 0x0E,
    'DATA64'            : 0x0F,
    'BOOLEAN'           : 0x10,
    'BITMAP8'           : 0x18,
    'BITMAP16'          : 0x19,
    'BITMAP24'          : 0x1A,
    'BITMAP32'          : 0x1B,
    'BITMAP40'          : 0x1C,
    'BITMAP48'          : 0x1D,
    'BITMAP56'          : 0x1E,
    'BITMAP64'          : 0x1F,
    'INT8U'             : 0x20,
    'INT16U'            : 0x21,
    'INT24U'            : 0x22,
    'INT32U'            : 0x23,
    'INT40U'            : 0x24,
    'INT48U'            : 0x25,
    'INT56U'            : 0x26,
    'INT64U'            : 0x27,
    'INT8S'             : 0x28,
    'INT16S'            : 0x29,
    'INT24S'            : 0x2A,
    'INT32S'            : 0x2B,
    'INT40S'            : 0x2C,
    'INT48S'            : 0x2D,
    'INT56S'            : 0x2E,
    'INT64S'            : 0x2F,
    'ENUM8'             : 0x30,
    'ENUM16'            : 0x31,
    'FLOAT_SEMI'        : 0x38,
    'FLOAT_SINGLE'      : 0x39,
    'FLOAT_DOUBLE'      : 0x3A,
    'OCTET_STRING'      : 0x41,
    'CHAR_STRING'       : 0x42,
    'LONG_OCTET_STRING' : 0x43,
    'LONG_CHAR_STRING'  : 0x44,
    'ARRAY'             : 0x48,
    'STRUCT'            : 0x4C,
    'SET'               : 0x50,
    'BAG'               : 0x51,
    'TIME_OF_DAY'       : 0xE0,
    'DATE'              : 0xE1,
    'UTC_TIME'          : 0xE2,
    'CLUSTER_ID'        : 0xE8,
    'ATTRIBUTE_ID'      : 0xE9,
    'BACNET_OID'        : 0xEA,
    'IEEE_ADDRESS'      : 0xF0,
    'SECURITY_KEY'      : 0xF1,
    'UNKNOWN'           : 0xFF
}

if __name__ == '__main__':
    import doctest
    doctest.testmod()

