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
    def __init__(self, cluster_code, code, arglist):
        self.cluster_code = cluster_code
        self.code = code
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
        return ZCLCommandCall(self.cluster_code, self.code, arglist)

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
    def __init__(self, attr_xml):
        self.name = attr_xml.text
        self.code = int(attr_xml.get('code'), 0)
        self.type = attr_xml.get('type')
        if self.type in ['INT16U', 'INT16S', 'ENUM16', 'BITMAP16']:
            self.size = 2
        else if self.type in ['INT32U', 'INT32S', 'ENUM32', 'BITMAP32', 'IEEE_ADDRESS']:
            self.size = 4
        else if self.type in ['CHAR_STRING', 'OCTET_STRING']:
            self.size = None
        else:
            self.size = 1

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

class ZBController():
    def __init__(self, xml_files = None):
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
        #TODO - need to include type ID somehow
        payload = _list_from_arg(attribute.type, value)
        self.conn.write('zcl global write 0x%04X 0x%04X {%s}' %
                attribute.cluster_code, attribute.code,
                " ".join(['%02X' % x for x in payload]))
        self.conn.write('send 0x%04X 1 1\n' % destination)

    #T000931A2:RX len 15, ep 01, clus 0x0101 (Door Lock) FC 09 seq 4E cmd 06 payload[06 00 01 00 06 06 36 37 38 39 30 30 ]
    def wait_for_command(self, command, timeout=10):
        '''
        Waits for an incomming message and validates it against the given
        cluster ID, command ID, and arguments. Any arguments given as None
        are ignored. Returns True for success or False for failure.
        '''
        # read and discard any data already queued up in the buffer
        self.conn.read_eager()
        _, match, _ = self.conn.expect(['RX len [0-9]+, ep [0-9A-Z]+, \
                clus 0x%04X \([a-zA-Z ]+\) .* cmd %02X payload\[([0-9A-Z ]*)]'
            % (command.cluster_code, command.code)], timeout=timeout)
        if match is None:
            print "TIMED OUT waiting for " + command.name
            return False
        else:
            payload = [int(x, 16) for x in match.group(1).split()]
            return _validate_payload(command.arglist, payload)

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
    if type in ['INT32U', 'IEEE_ADDRESS', 'BITMAP32']:
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
    if type in ['INT32U', 'IEEE_ADDRESS', 'BITMAP32']:
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


if __name__ == '__main__':
    import doctest
    doctest.testmod()

#  ZCL_NO_DATA_ATTRIBUTE_TYPE                        = 0x00, // No data
#  ZCL_DATA8_ATTRIBUTE_TYPE                          = 0x08, // 8-bit data
#  ZCL_DATA16_ATTRIBUTE_TYPE                         = 0x09, // 16-bit data
#  ZCL_DATA24_ATTRIBUTE_TYPE                         = 0x0A, // 24-bit data
#  ZCL_DATA32_ATTRIBUTE_TYPE                         = 0x0B, // 32-bit data
#  ZCL_DATA40_ATTRIBUTE_TYPE                         = 0x0C, // 40-bit data
#  ZCL_DATA48_ATTRIBUTE_TYPE                         = 0x0D, // 48-bit data
#  ZCL_DATA56_ATTRIBUTE_TYPE                         = 0x0E, // 56-bit data
#  ZCL_DATA64_ATTRIBUTE_TYPE                         = 0x0F, // 64-bit data
#  ZCL_BOOLEAN_ATTRIBUTE_TYPE                        = 0x10, // Boolean
#  ZCL_BITMAP8_ATTRIBUTE_TYPE                        = 0x18, // 8-bit bitmap
#  ZCL_BITMAP16_ATTRIBUTE_TYPE                       = 0x19, // 16-bit bitmap
#  ZCL_BITMAP24_ATTRIBUTE_TYPE                       = 0x1A, // 24-bit bitmap
#  ZCL_BITMAP32_ATTRIBUTE_TYPE                       = 0x1B, // 32-bit bitmap
#  ZCL_BITMAP40_ATTRIBUTE_TYPE                       = 0x1C, // 40-bit bitmap
#  ZCL_BITMAP48_ATTRIBUTE_TYPE                       = 0x1D, // 48-bit bitmap
#  ZCL_BITMAP56_ATTRIBUTE_TYPE                       = 0x1E, // 56-bit bitmap
#  ZCL_BITMAP64_ATTRIBUTE_TYPE                       = 0x1F, // 64-bit bitmap
#  ZCL_INT8U_ATTRIBUTE_TYPE                          = 0x20, // Unsigned 8-bit integer
#  ZCL_INT16U_ATTRIBUTE_TYPE                         = 0x21, // Unsigned 16-bit integer
#  ZCL_INT24U_ATTRIBUTE_TYPE                         = 0x22, // Unsigned 24-bit integer
#  ZCL_INT32U_ATTRIBUTE_TYPE                         = 0x23, // Unsigned 32-bit integer
#  ZCL_INT40U_ATTRIBUTE_TYPE                         = 0x24, // Unsigned 40-bit integer
#  ZCL_INT48U_ATTRIBUTE_TYPE                         = 0x25, // Unsigned 48-bit integer
#  ZCL_INT56U_ATTRIBUTE_TYPE                         = 0x26, // Unsigned 56-bit integer
#  ZCL_INT64U_ATTRIBUTE_TYPE                         = 0x27, // Unsigned 64-bit integer
#  ZCL_INT8S_ATTRIBUTE_TYPE                          = 0x28, // Signed 8-bit integer
#  ZCL_INT16S_ATTRIBUTE_TYPE                         = 0x29, // Signed 16-bit integer
#  ZCL_INT24S_ATTRIBUTE_TYPE                         = 0x2A, // Signed 24-bit integer
#  ZCL_INT32S_ATTRIBUTE_TYPE                         = 0x2B, // Signed 32-bit integer
#  ZCL_INT40S_ATTRIBUTE_TYPE                         = 0x2C, // Signed 40-bit integer
#  ZCL_INT48S_ATTRIBUTE_TYPE                         = 0x2D, // Signed 48-bit integer
#  ZCL_INT56S_ATTRIBUTE_TYPE                         = 0x2E, // Signed 56-bit integer
#  ZCL_INT64S_ATTRIBUTE_TYPE                         = 0x2F, // Signed 64-bit integer
#  ZCL_ENUM8_ATTRIBUTE_TYPE                          = 0x30, // 8-bit enumeration
#  ZCL_ENUM16_ATTRIBUTE_TYPE                         = 0x31, // 16-bit enumeration
#  ZCL_FLOAT_SEMI_ATTRIBUTE_TYPE                     = 0x38, // Semi-precision
#  ZCL_FLOAT_SINGLE_ATTRIBUTE_TYPE                   = 0x39, // Single precision
#  ZCL_FLOAT_DOUBLE_ATTRIBUTE_TYPE                   = 0x3A, // Double precision
#  ZCL_OCTET_STRING_ATTRIBUTE_TYPE                   = 0x41, // Octet string
#  ZCL_CHAR_STRING_ATTRIBUTE_TYPE                    = 0x42, // Character string
#  ZCL_LONG_OCTET_STRING_ATTRIBUTE_TYPE              = 0x43, // Long octet string
#  ZCL_LONG_CHAR_STRING_ATTRIBUTE_TYPE               = 0x44, // Long character string
#  ZCL_ARRAY_ATTRIBUTE_TYPE                          = 0x48, // Array
#  ZCL_STRUCT_ATTRIBUTE_TYPE                         = 0x4C, // Structure
#  ZCL_SET_ATTRIBUTE_TYPE                            = 0x50, // Set
#  ZCL_BAG_ATTRIBUTE_TYPE                            = 0x51, // Bag
#  ZCL_TIME_OF_DAY_ATTRIBUTE_TYPE                    = 0xE0, // Time of day
#  ZCL_DATE_ATTRIBUTE_TYPE                           = 0xE1, // Date
#  ZCL_UTC_TIME_ATTRIBUTE_TYPE                       = 0xE2, // UTC Time
#  ZCL_CLUSTER_ID_ATTRIBUTE_TYPE                     = 0xE8, // Cluster ID
#  ZCL_ATTRIBUTE_ID_ATTRIBUTE_TYPE                   = 0xE9, // Attribute ID
#  ZCL_BACNET_OID_ATTRIBUTE_TYPE                     = 0xEA, // BACnet OID
#  ZCL_IEEE_ADDRESS_ATTRIBUTE_TYPE                   = 0xF0, // IEEE address
#  ZCL_SECURITY_KEY_ATTRIBUTE_TYPE                   = 0xF1, // 128-bit security key
#  ZCL_UNKNOWN_ATTRIBUTE_TYPE                        = 0xFF // Unknown
