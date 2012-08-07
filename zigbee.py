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
    def __init__(self, cluster_id, command_id, payload):
        '''Takes a ZCL Command prototype (instance of ZCLCommand) and an
        argument list and creates a ZCLCommandCall instance with the
        arguments encoded into a payload (list of bytes)'''
        self.cluster_id = cluster_id
        self.command_id = command_id
        # copy the list to make sure there's no interaction with the given payload
        self.payload = list(payload)

class ZCLCommandPrototype:
    '''ZCLCommandPrototype represents the call signiture of a ZCL Command.
    It is also callable, and when called will return a ZCLCommandCall object
    with the cluster ID, command ID, and a payload list generated from the
    type signature and the arguments given to the call.'''
    def __init__(self, cluster_id, cmd_xml):
        # a ZCLCommandPrototype needs to know about its cluster ID so that it
        # can generate a proper ZCLCommandCall that can be passed to actually
        # send a message
        self.cluster_id = cluster_id
        self.name = cmd_xml.get('name')
        self.code = int(cmd_xml.get('code'), 0)
        # function parameters are mistakenly called 'args' in the xml
        self.params = [ZCLCommandParam(xml) for xml in cmd_xml.findall('arg')]
    def __call__(self, *args):
        if len(args) != len(self.params):
            raise TypeError("%s() takes exactly %d arguments (%d given)\n" %
                    (_attr_from_name(self.name), len(self.params), len(args)) +
                    "\n".join(["\t\t%s (%s)" % (param.name, param.type) for
                        param in self.params]))
        payload = []
        for type, arg in zip([x.type for x in self.params], args):
            payload += _list_from_arg(type, arg)
        return ZCLCommandCall(self.cluster_id, self.code, payload)

class ZCLCommandParam:
    def __init__(self, param_xml):
        self.name = param_xml.get('name')
        self.type = param_xml.get('type')

class ZCLAttribute:
    def __init__(self, attr_xml):
        self.name = attr_xml.text
        self.code = int(attr_xml.get('code'), 0)
        self.type = attr_xml.get('type')

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

class ZBController(Telnet):
    def __init__(self, xml_files = None):
        Telnet.__init__(self)
        self.sequence = 0

    def open(self, hostname):
        Telnet.open(self, hostname, 4900)

    def _network_command(self, command, args, status_prefix):
        self.write('network %s %s\n' % (command, args))
        _, match, _ = self.expect(['%s (0x[0-9A-F]{2})' % status_prefix], timeout=2)
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
            out = self.read_until('EMBER_NETWORK_DOWN', timeout=2)
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
        _, match, _ = self.expect(['Device Announce: (0x[0-9A-F]{4})'])
        if match is None:
            raise TimeoutError()
        print 'Device %s joined' % match.group(1)
        return int(match.group(1), 0)

    def send_zcl_command(self, destination, cmd):
        self.write('raw 0x%04X {01 %02X %02X %s}\n' %
                (cmd.cluster_id, self.sequence, cmd.command_id,
                " ".join(["%02X" % x for x in cmd.payload])))
        self.write('send 0x%04X 1 1\n' % destination)
        self.sequence = self.sequence + 1 % 0x100

    #T000931A2:RX len 15, ep 01, clus 0x0101 (Door Lock) FC 09 seq 4E cmd 06 payload[06 00 01 00 06 06 36 37 38 39 30 30 ]
    def wait_for_command(self, command):
        "Returns the payload as a list of ints"
        # read and discard any data already queued up in the buffer
        self.read_eager()
        _, match, _ = self.expect(['RX len [0-9]+, ep [0-9A-Z]+, clus 0x%04X \([a-zA-Z ]+\) .* cmd %02X payload\[([0-9A-Z ]*)]'
            % (command.cluster_id,command.code)], timeout=10)
        if match is None:
            print "TIMED OUT waiting for " + command.name
            return []
        return [int(x, 16) for x in match.group(1).split()]

class TimeoutError(StandardError):
    pass

class UnhandledStatusError(StandardError):
    pass

def _attr_from_name(name):
    '''This assumes that the name is either in CamelCase or
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
    '''Takes in a type string and a value and returns the value converted
    into a list suitable for a ZCL payload.
    >>> _list_from_arg('INT8U', 0x30)
    [48]
    >>> _list_from_arg('CHAR_STRING', '6789')
    [4, 54, 55, 56, 57]
    >>> _list_from_arg('OCTET_STRING', [6, 7, 8, 9])
    [4, 6, 7, 8, 9]'''
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
    if type == 'INT16S':
        if value < -32768 or value > 32767:
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

if __name__ == '__main__':
    import doctest
    doctest.testmod()
